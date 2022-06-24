from collections import Counter

import simplejson
from annoying.functions import get_object_or_None
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.search import TrigramDistance
from django.core.cache import cache
from django.db.models import Q, QuerySet, Value
from django.db.models.functions import Concat, Lower
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from djangorestframework_camel_case.parser import CamelCaseJSONParser
from djangorestframework_camel_case.render import CamelCaseJSONRenderer
from haystack.query import SearchQuerySet
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import get_object_or_404
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST

from astrobin.models import GearMigrationStrategy, Image
from astrobin_apps_equipment.api.permissions.is_equipment_moderator_or_own_migrator_or_readonly import \
    IsEquipmentModeratorOrOwnMigratorOrReadOnly
from astrobin_apps_equipment.api.throttle import EquipmentCreateThrottle
from astrobin_apps_equipment.models import EquipmentBrand, EquipmentItem
from astrobin_apps_equipment.models.equipment_item import EquipmentItemReviewerDecision
from astrobin_apps_equipment.models.equipment_item_group import EquipmentItemKlass, EquipmentItemUsageType
from astrobin_apps_equipment.services import EquipmentService
from astrobin_apps_equipment.services.equipment_item_service import EquipmentItemService
from astrobin_apps_notifications.utils import build_notification_url, push_notification
from astrobin_apps_premium.services.premium_service import PremiumService
from astrobin_apps_premium.templatetags.astrobin_apps_premium_tags import can_access_full_search
from common.services import AppRedirectionService


class EquipmentItemViewSet(viewsets.ModelViewSet):
    renderer_classes = [BrowsableAPIRenderer, CamelCaseJSONRenderer]
    parser_classes = [CamelCaseJSONParser]
    permission_classes = [IsEquipmentModeratorOrOwnMigratorOrReadOnly]
    http_method_names = ['get', 'post', 'head']
    throttle_classes = [EquipmentCreateThrottle]

    def get_queryset(self) -> QuerySet:
        q = self.request.query_params.get('q')
        sort = self.request.query_params.get('sort')

        manager = self.get_serializer().Meta.model.objects
        queryset = manager.all()

        if 'include-variants' in self.request.query_params and self.request.query_params.get(
                'include-variants'
        ).lower() == 'false':
            queryset = queryset.filter(variant_of__isnull=True)

        if 'EditProposal' not in str(self.get_serializer().Meta.model):
            if self.request.user.is_authenticated:
                if not self.request.user.groups.filter(name='equipment_moderators').exists():
                    queryset = queryset.filter(Q(brand__isnull=False) | Q(created_by=self.request.user))
            else:
                queryset = queryset.filter(brand__isnull=False)

        if q:
            brand = get_object_or_None(EquipmentBrand, name__iexact=q)
            brand_queryset: QuerySet = queryset.none()
            if brand:
                brand_queryset = queryset.filter(
                    Q(brand=brand) &
                    Q(
                        Q(reviewer_decision=EquipmentItemReviewerDecision.APPROVED) |
                        Q(created_by=self.request.user)
                    )
                ).order_by(Lower('name'))
            if brand_queryset.exists():
                queryset = brand_queryset
            else:
                queryset = queryset.annotate(
                    full_name=Concat('brand__name', Value(' '), 'name'),
                    distance=TrigramDistance('full_name', q)
                ).filter(
                    Q(
                        Q(distance__lte=.8) | Q(full_name__icontains=q)
                    ) &
                    Q(
                        Q(reviewer_decision=EquipmentItemReviewerDecision.APPROVED) |
                        Q(created_by=self.request.user)
                    )
                ).order_by(
                    'distance',
                    Lower('brand__name'),
                    Lower('name'),
                )
        elif sort == 'az':
            queryset = queryset.order_by(Lower('brand__name'), Lower('name'))
        elif sort == '-az':
            queryset = queryset.order_by(Lower('brand__name'), Lower('name')).reverse()
        elif sort == 'users':
            queryset = queryset.order_by('user_count', Lower('brand__name'), Lower('name'))
        elif sort == '-users':
            queryset = queryset.order_by('-user_count', Lower('brand__name'), Lower('name'))
        elif sort == 'images':
            queryset = queryset.order_by('image_count', Lower('brand__name'), Lower('name'))
        elif sort == '-images':
            queryset = queryset.order_by('-image_count', Lower('brand__name'), Lower('name'))

        return queryset

    @action(
        detail=True,
        methods=['get'],
    )
    def variants(self, request, pk):
        manager = self.get_serializer().Meta.model.objects
        item: EquipmentItem = get_object_or_404(manager, pk=pk)

        queryset = item.variants.all()
        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data)

    @action(
        detail=False,
        methods=['GET'],
        url_path='recently-used'
    )
    def find_recently_used(self, request):
        manager = self.get_serializer().Meta.model.objects
        objects = manager.none()

        from astrobin_apps_equipment.models import Sensor
        from astrobin_apps_equipment.models import Camera
        from astrobin_apps_equipment.models import Telescope
        from astrobin_apps_equipment.models import Mount
        from astrobin_apps_equipment.models import Filter
        from astrobin_apps_equipment.models import Accessory
        from astrobin_apps_equipment.models import Software

        if manager.model == Sensor:
            return Response("This API does not support sensors", HTTP_400_BAD_REQUEST)

        if request.user.is_authenticated:
            usage_type = request.query_params.get('usage-type')
            recent_items = []
            images: QuerySet[Image] = Image.objects_including_wip.filter(user=request.user).order_by('-uploaded')

            image: Image
            for image in images.iterator():
                if len(recent_items) > 5:
                    break

                property: str
                if manager.model == Camera:
                    if usage_type == 'imaging':
                        property = 'imaging_cameras_2'
                    elif usage_type == 'guiding':
                        property = 'guiding_cameras_2'
                    else:
                        return Response("You need to specify a 'usage_type' with cameras", HTTP_400_BAD_REQUEST)
                elif manager.model == Telescope:
                    if usage_type == 'imaging':
                        property = 'imaging_telescopes_2'
                    elif usage_type == 'guiding':
                        property = 'guiding_telescopes_2'
                    else:
                        return Response("You need to specify a 'usage_type' with telescopes", HTTP_400_BAD_REQUEST)
                elif manager.model == Mount:
                    property = 'mounts_2'
                elif manager.model == Filter:
                    property = 'filters_2'
                elif manager.model == Accessory:
                    property = 'accessories_2'
                elif manager.model == Software:
                    property = 'software_2'

                for x in getattr(image, property).all():
                    recent_items.append(x.pk)

            objects = manager.filter(pk__in=recent_items)

        serializer = self.serializer_class(objects, many=True)
        return Response(serializer.data)

    @action(
        detail=False,
        methods=['GET'],
        url_path='find-similar-in-brand',
    )
    def find_similar_in_brand(self, request):
        brand = request.GET.get('brand')
        q = request.GET.get('q')

        manager = self.get_serializer().Meta.model.objects
        objects = manager.none()

        if brand and q:
            objects = manager.annotate(
                distance=TrigramDistance('name', q)
            ).filter(
                Q(brand=int(brand)) &
                Q(Q(distance__lte=.7) | Q(name__icontains=q)) &
                ~Q(name=q)
            ).order_by(
                'distance'
            )[:10]

        serializer = self.serializer_class(objects, many=True)
        return Response(serializer.data)

    @action(
        detail=False,
        methods=['GET'],
        url_path='others-in-brand',
    )
    def others_in_brand(self, request):
        brand = request.query_params.get('brand')
        name = request.query_params.get('name')

        manager = self.get_serializer().Meta.model.objects
        objects = manager.none()

        if brand:
            objects = manager.filter(brand=int(brand)).order_by('name')
            if name:
                objects = objects.exclude(name__iexact=name)

        serializer = self.serializer_class(objects, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['POST'])
    def approve(self, request, pk):
        if not request.user.groups.filter(name='equipment_moderators').exists():
            raise PermissionDenied(request.user)

        item = get_object_or_404(self.get_serializer().Meta.model.objects, pk=pk)

        if item.reviewed_by is not None:
            return Response("This item was already reviewed", HTTP_400_BAD_REQUEST)

        if item.created_by == request.user:
            return Response("You cannot review an item that you created", HTTP_400_BAD_REQUEST)

        item.reviewed_by = request.user
        item.reviewed_timestamp = timezone.now()
        item.reviewer_decision = EquipmentItemReviewerDecision.APPROVED
        item.reviewer_comment = request.data.get('comment')

        if item.created_by and item.created_by != request.user:
            push_notification(
                [item.created_by],
                request.user,
                'equipment-item-approved',
                {
                    'user': request.user.userprofile.get_display_name(),
                    'user_url': build_notification_url(
                        settings.BASE_URL + reverse('user_page', args=(request.user.username,))
                    ),
                    'item': f'{item.brand.name if item.brand else _("(DIY)")} {item.name}',
                    'item_url': build_notification_url(
                        AppRedirectionService.redirect(
                            f'/equipment/explorer/{EquipmentItemService(item).get_type()}/{item.pk}'
                        )
                    ),
                    'comment': item.reviewer_comment,
                }
            )

        item.save()

        serializer = self.serializer_class(item)
        return Response(serializer.data)

    @action(detail=True, methods=['POST'])
    def reject(self, request, pk):
        from astrobin_apps_equipment.models import Sensor
        from astrobin_apps_equipment.models import Camera
        from astrobin_apps_equipment.models import CameraEditProposal
        from astrobin_apps_equipment.models import Telescope
        from astrobin_apps_equipment.models import Mount
        from astrobin_apps_equipment.models import Filter
        from astrobin_apps_equipment.models import Accessory
        from astrobin_apps_equipment.models import Software

        if not request.user.groups.filter(name='equipment_moderators').exists():
            raise PermissionDenied(request.user)

        model = self.get_serializer().Meta.model
        item: EquipmentItem = get_object_or_404(model.objects, pk=pk)

        if item.reviewed_by is not None and item.reviewer_decision == EquipmentItemReviewerDecision.APPROVED:
            return Response("This item was already approved", HTTP_400_BAD_REQUEST)

        if item.created_by == request.user:
            return Response("You cannot review an item that you created", HTTP_400_BAD_REQUEST)

        item.reviewed_by = request.user
        item.reviewed_timestamp = timezone.now()
        item.reviewer_decision = EquipmentItemReviewerDecision.REJECTED
        item.reviewer_rejection_reason = request.data.get('reason')
        item.reviewer_comment = request.data.get('comment')
        item.reviewer_rejection_duplicate_of_klass = request.data.get('duplicate_of_klass', item.klass)
        item.reviewer_rejection_duplicate_of_usage_type = request.data.get('duplicate_of_usage_type')
        item.reviewer_rejection_duplicate_of = request.data.get('duplicate_of')

        duplicate_of = None
        duplicate_model = {
            EquipmentItemKlass.TELESCOPE: Telescope,
            EquipmentItemKlass.CAMERA: Camera,
            EquipmentItemKlass.MOUNT: Mount,
            EquipmentItemKlass.FILTER: Filter,
            EquipmentItemKlass.ACCESSORY: Accessory,
            EquipmentItemKlass.SOFTWARE: Software
        }.get(item.reviewer_rejection_duplicate_of_klass)

        if item.reviewer_rejection_duplicate_of:
            try:
                duplicate_of = duplicate_model.objects.get(pk=item.reviewer_rejection_duplicate_of)
            except model.DoesNotExist:
                duplicate_of = None
                item.reviewer_rejection_duplicate_of = None
                item.reviewer_rejection_duplicate_of_klass = None
                item.reviewer_rejection_duplicate_of_klass_usage_type = None

        if item.created_by and item.created_by != request.user:
            push_notification(
                [item.created_by],
                request.user,
                'equipment-item-rejected',
                {
                    'user': request.user.userprofile.get_display_name(),
                    'user_url': build_notification_url(
                        settings.BASE_URL + reverse('user_page', args=(request.user.username,))
                    ),
                    'item': f'{item.brand.name if item.brand else _("(DIY)")} {item.name}',
                    'reject_reason': item.reviewer_rejection_reason,
                    'comment': item.reviewer_comment,
                    'duplicate_of': duplicate_of,
                    'duplicate_of_url': build_notification_url(
                        AppRedirectionService.redirect(
                            f'/equipment'
                            f'/explorer'
                            f'/{duplicate_of.item_type}/{duplicate_of.pk}'
                            f'/{duplicate_of.slug}'
                        )
                    ) if duplicate_of else None,
                }
            )

        migration_strategies: QuerySet = GearMigrationStrategy.objects.filter(
            user=item.created_by,
            migration_flag='MIGRATE',
            migration_content_type=ContentType.objects.get_for_model(model),
            migration_object_id=item.id,
        )

        if duplicate_of:
            migration_strategies.update(
                migration_object_id=duplicate_of.pk,
                migration_content_type=ContentType.objects.get_for_model(duplicate_model)
            )
        else:
            for migration_strategy in migration_strategies:
                EquipmentService.undo_migration_strategy(migration_strategy)

        affected_images = []
        for prop in (
            'imaging_telescopes_2',
            'imaging_cameras_2',
            'mounts_2',
            'guiding_telescopes_2',
            'guiding_cameras_2',
            'filters_2',
            'accessories_2',
            'software_2',
        ):
            try:
                images = Image.objects_including_wip.filter(**{prop: item})
            except ValueError:
                images = None

            if images is not None and images.count() > 0:
                for image in images.iterator():
                    affected_images.append(dict(image=image, prop=prop))

        for affected in affected_images:
            image: Image = affected.get("image")
            prop: str = affected.get("prop")

            if duplicate_of:
                if model == duplicate_model:
                    getattr(image, prop).add(duplicate_of)
                else:
                    destination_map = {
                        EquipmentItemKlass.TELESCOPE: 'imaging_telescopes_2' \
                            if item.reviewer_rejection_duplicate_of_usage_type == EquipmentItemUsageType.IMAGING \
                            else 'guiding_telescopes_2',
                        EquipmentItemKlass.CAMERA: 'imaging_cameras_2' \
                            if item.reviewer_rejection_duplicate_of_usage_type == EquipmentItemUsageType.IMAGING \
                            else 'guiding_cameras_2',
                        EquipmentItemKlass.MOUNT: 'mounts_2',
                        EquipmentItemKlass.FILTER: 'filters_2',
                        EquipmentItemKlass.ACCESSORY: 'accessories_2',
                        EquipmentItemKlass.SOFTWARE: 'software_2',
                    }
                    getattr(image, destination_map.get(duplicate_of.klass)).add(duplicate_of)

            push_notification(
                [item.created_by],
                request.user,
                'equipment-item-rejected-affected-image',
                {
                    'user': request.user.userprofile.get_display_name(),
                    'user_url': build_notification_url(
                        settings.BASE_URL + reverse('user_page', args=(request.user.username,))
                    ),
                    'item': f'{item.brand.name if item.brand else _("(DIY)")} {item.name}',
                    'reject_reason': item.reviewer_rejection_reason,
                    'comment': item.reviewer_comment,
                    'duplicate_of': duplicate_of,
                    'duplicate_of_url': build_notification_url(
                        AppRedirectionService.redirect(
                            f'/equipment'
                            f'/explorer'
                            f'/{duplicate_of.item_type}/{duplicate_of.pk}'
                            f'/{duplicate_of.slug}'
                        )
                    ) if duplicate_of else None,
                    'image_url': build_notification_url(
                        settings.BASE_URL + reverse('image_detail', args=(image.get_id(),))
                    ),
                    'image_title': image.title,
                }
            )

        if item.klass == EquipmentItemKlass.SENSOR:
            Camera.all_objects.filter(sensor=item).update(sensor=None)
            CameraEditProposal.all_objects.filter(sensor=item).update(sensor=None)

        item.delete()

        if item.brand:
            brand_has_items = False
            for klass in (Sensor, Camera, Telescope, Mount, Filter, Accessory, Software):
                if klass.objects.filter(brand=item.brand).exists():
                    brand_has_items = True
                    break

            if not brand_has_items:
                item.brand.delete()

        serializer = self.serializer_class(item)
        return Response(serializer.data)

    @action(detail=True, methods=['GET'], url_path='users')
    def users(self, request, pk: int) -> Response:
        cache_key: str = f'equipment_item_view_set_{self.get_object().__class__.__name__}_{pk}_users'
        data = cache.get(cache_key)

        if data is None:
            sqs: SearchQuerySet = SearchQuerySet().models(self.get_serializer().Meta.model).filter(django_id=pk)

            if sqs.count() > 0:
                data = sqs[0].equipment_item_users
            else:
                data = '[]'

            cache.set(cache_key, data, 60*60*12)

        return Response(simplejson.loads(data))

    @action(detail=True, methods=['GET'], url_path='images')
    def images(self, request, pk: int) -> Response:
        cache_key: str = f'equipment_item_view_set_{self.get_object().__class__.__name__}_{pk}_images'
        data = cache.get(cache_key)

        if data is None:
            sqs: SearchQuerySet = SearchQuerySet().models(self.get_serializer().Meta.model).filter(django_id=pk)

            if sqs.count() > 0:
                data = sqs[0].equipment_item_images
            else:
                data = '[]'

            cache.set(cache_key, data, 60 * 60 * 12)

        return Response(simplejson.loads(data))

    @action(detail=True, methods=['GET'], url_path='most-often-used-with')
    def most_often_used_with(self, request, pk: int) -> Response:
        valid_subscription = PremiumService(request.user).get_valid_usersubscription()
        can_access = can_access_full_search(valid_subscription)
        cache_key: str = f'equipment_item_view_set_{self.get_object().__class__.__name__}_{pk}_most_often_used_with_{can_access}'
        data = cache.get(cache_key)

        if data is None:
            sqs: SearchQuerySet = SearchQuerySet().models(self.get_serializer().Meta.model).filter(django_id=pk)

            if sqs.count() > 0:
                data = sqs[0].equipment_item_most_often_used_with
            else:
                data = '{}'

            if not can_access:
                # Restrict to the top item.
                parsed = dict(Counter(simplejson.loads(data)).most_common(1))
                data = simplejson.dumps(parsed)

            cache.set(cache_key, data, 60 * 60 * 12)

        return Response(simplejson.loads(data))

    def image_upload(self, request, pk):
        obj = self.get_object()
        serializer = self.serializer_class(obj, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, HTTP_400_BAD_REQUEST)

    class Meta:
        abstract = True

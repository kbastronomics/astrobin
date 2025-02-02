import logging
import math
from datetime import timedelta
from typing import List, Optional, Tuple, Union

import numpy as np
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key
from django.db.models import Q, QuerySet
from django.utils import timezone
from django.utils.translation import ugettext as _
from haystack.query import SearchQuerySet
from pybb.models import Post
from safedelete import HARD_DELETE
from safedelete.queryset import SafeDeleteQueryset
from subscription.models import Subscription

from astrobin.enums import SubjectType
from common.services.constellations_service import ConstellationsService
from nested_comments.models import NestedComment
from toggleproperties.models import ToggleProperty

log = logging.getLogger('apps')


class UserService:
    user: Optional[User] = None

    def __init__(self, user: Optional[User]):
        self.user = user

    @staticmethod
    def get_case_insensitive(username):
        case_insensitive_matches = User.objects \
            .select_related('userprofile') \
            .prefetch_related('groups') \
            .filter(username__iexact=username)

        count = case_insensitive_matches.count()

        if count == 0:
            raise User.DoesNotExist

        if count == 1:
            return case_insensitive_matches.first()

        return User.objects \
            .select_related('userprofile') \
            .prefetch_related('groups') \
            .get(username__exact=username)

    @staticmethod
    def get_users_in_group_sample(group_name, percent, exclude=None):
        # type: (str, int, User) -> list[User]
        try:
            users = User.objects.filter(groups=Group.objects.get(name=group_name))
            if exclude:
                users = users.exclude(pk=exclude.pk)

            return np.random.choice(list(users), int(math.ceil(users.count() / 100.0 * percent)), replace=False)
        except Group.DoesNotExist:
            return []

    def get_all_images(self) -> QuerySet:
        from astrobin.models import Image
        return Image.objects_including_wip.filter(user=self.user)

    def get_public_images(self) -> QuerySet:
        from astrobin.models import Image
        return Image.objects.filter(user=self.user)

    def get_wip_images(self) -> QuerySet:
        from astrobin.models import Image
        return Image.wip.filter(user=self.user)

    def get_deleted_images(self) -> QuerySet:
        from astrobin.models import Image
        return Image.deleted_objects.filter(user=self.user)

    def get_bookmarked_images(self) -> QuerySet:
        from astrobin.models import Image

        image_ct = ContentType.objects.get_for_model(Image)  # type: ContentType
        bookmarked_pks: List[int] = [x.object_id for x in \
                          ToggleProperty.objects.toggleproperties_for_user("bookmark", self.user).filter(
                              content_type=image_ct)
                          ]

        return Image.objects.filter(pk__in=bookmarked_pks)

    def get_liked_images(self) -> QuerySet:
        from astrobin.models import Image

        image_ct = ContentType.objects.get_for_model(Image)  # type: ContentType
        liked_pks = [
            x.object_id for x in \
            ToggleProperty.objects.toggleproperties_for_user("like", self.user).filter(content_type=image_ct)
        ]  # type: List[int]

        return Image.objects.filter(pk__in=liked_pks)

    def get_image_numbers(self):
        public = self.get_public_images()
        wip = self.get_wip_images()

        return {
            'public_images_no': public.count(),
            'wip_images_no': wip.count(),
            'deleted_images_no': self.get_deleted_images().count(),
        }

    def get_profile_stats(self, request_language: str):
        if not self.user:
            return {}
        
        user = self.user
        key = f'User.{self.user.pk}.Stats.{request_language}'
        data = cache.get(key)
        if not data:
            user_sqs = SearchQuerySet().models(User).filter(django_id=self.user.pk)
            data = {}

            if user_sqs.count() > 0:
                result = user_sqs[0]
                
                try:
                    data['stats'] = (
                        (_('Member since'), user.date_joined \
                            if user.userprofile.display_member_since \
                            else None, 'datetime'),
                        (_('Last seen online'), user.userprofile.last_seen or user.last_login \
                            if user.userprofile.display_last_seen \
                            else None, 'datetime'),
                        (_('Total integration time'),
                         "%.1f %s" % (result.integration, _("hours")) if result.integration else None),
                        (_('Average integration time'),
                         "%.1f %s" % (result.avg_integration, _("hours")) if user_sqs[
                             0].avg_integration else None),
                        (_('Forum posts written'), "%d" % result.forum_posts if result.forum_posts else 0),
                        (_('Comments written'),
                         "%d" % result.comments_written if result.comments_written else 0),
                        (_('Comments received'), "%d" % result.comments if result.comments else 0),
                        (_('Likes received'),
                         "%d" % result.total_likes_received if result.total_likes_received else 0),
                        (_('Views received'), "%d" % result.views if result.views else 0),
                    )
                except Exception as e:
                    log.error("User page (%d): unable to get stats from search index: %s" % (user.pk, str(e)))
                else:
                    cache.set(key, data, 300)
            else:
                log.error("User page (%d): unable to get user's SearchQuerySet" % user.pk)
                data = {}

        return data

    def shadow_bans(self, other):
        # type: (User) -> bool

        if not hasattr(self.user, 'userprofile') or not hasattr(other, 'userprofile'):
            return False

        return other.userprofile in self.user.userprofile.shadow_bans.all()

    def _real_can_like(self, obj):
        if self.user.is_superuser:
            return True, None

        if not self.user.is_authenticated:
            return False, "ANONYMOUS"

        if obj.__class__.__name__ == 'Image':
            return self.user != obj.user, "OWNER"
        elif obj.__class__.__name__ == 'NestedComment':
            return self.user != obj.author, "OWNER"
        elif obj.__class__.__name__ == 'Post':
            if self.user == obj.user:
                return False, "OWNER"
            if obj.topic.closed:
                return False, "TOPIC_CLOSED"
            return True, None

        return False, "UNKNOWN"

    def can_like(self, obj):
        return self._real_can_like(obj)[0]

    def can_like_reason(self, obj):
        return self._real_can_like(obj)[1]

    def _real_can_unlike(self, obj):
        if not self.user.is_authenticated:
            return False, "ANONYMOUS"

        toggle_properties = ToggleProperty.objects.toggleproperties_for_object('like', obj, self.user)
        if toggle_properties.exists():
            one_hour_ago = timezone.now() - timedelta(hours=1)
            if toggle_properties.first().created_on > one_hour_ago:
                return True, None
            return False, "TOO_LATE"

        return False, "NEVER_LIKED"

    def can_unlike(self, obj):
        return self._real_can_unlike(obj)[0]

    def can_unlike_reason(self, obj):
        return self._real_can_unlike(obj)[1]

    def get_all_comments(self):
        return NestedComment.objects.filter(author=self.user, deleted=False)

    def get_all_forum_posts(self):
        return Post.objects.filter(user=self.user)

    def received_likes_count(self):
        likes = 0

        for image in self.get_all_images().iterator():
            likes += image.likes()

        for comment in self.get_all_comments().iterator():
            likes += len(comment.likes)

        for post in self.get_all_forum_posts().iterator():
            likes += ToggleProperty.objects.filter(
                object_id=post.pk,
                content_type=ContentType.objects.get_for_model(Post),
                property_type='like'
            ).count()

        return likes

    def clear_gallery_image_list_cache(self):
        sections = ('public',)
        subsections = ('title', 'uploaded',)
        views = ('default', 'table',)
        languages = settings.LANGUAGES

        def _do_clear(language_to_clear, section_to_clear, subsection_to_clear, view_to_clear):
            key = make_template_fragment_key(
                'user_gallery_image_list2',
                [self.user.pk, language_to_clear, section_to_clear, subsection_to_clear, view_to_clear]
            )
            cache.delete(key)

        for language in languages:
            for section in sections:
                for subsection in subsections:
                    for view in views:
                        _do_clear(language[0], section, subsection, view)

    def empty_trash(self) -> int:
        from astrobin.models import Image

        images: SafeDeleteQueryset = Image.deleted_objects.filter(user=self.user)
        count: int = images.count()

        images.delete(force_policy=HARD_DELETE)

        return count

    def display_wip_images_on_public_gallery(self) -> bool:
        return self.user.userprofile.display_wip_images_on_public_gallery in (None, True)

    def sort_gallery_by(self, queryset: QuerySet, subsection: str, active: str, klass: str) -> Tuple[QuerySet, List[str]]:
        from astrobin.models import Acquisition, Camera, Image, Telescope
        from astrobin_apps_equipment.models import Camera as CameraV2, Telescope as TelescopeV2
        from astrobin_apps_images.services import ImageService

        menu = []

        #########
        # TITLE #
        #########
        if subsection == 'title':
            queryset = queryset.order_by('title')

        ############
        # UPLOADED #
        ############
        if subsection == 'uploaded':
            queryset = queryset.order_by('-published', '-uploaded')

        ############
        # ACQUIRED #
        ############
        elif subsection == 'acquired':
            last_acquisition_date_sql = 'SELECT date FROM astrobin_acquisition ' \
                                        'WHERE date IS NOT NULL AND image_id = astrobin_image.id ' \
                                        'ORDER BY date DESC ' \
                                        'LIMIT 1'
            queryset = queryset \
                .filter(acquisition__isnull=False) \
                .extra(
                select={'last_acquisition_date': last_acquisition_date_sql},
                order_by=['-last_acquisition_date', '-published']
            ) \
                .distinct()

        ########
        # YEAR #
        ########
        elif subsection == 'year':
            acquisitions = Acquisition.objects.filter(
                image__user=self.user,
                image__is_wip=False,
                image__deleted=None
            )
            if acquisitions:
                distinct_years = sorted(list(set([a.date.year for a in acquisitions if a.date])), reverse=True)
                no_date_message = _("No date specified")
                menu = [(str(year), str(year)) for year in distinct_years] + [('0', no_date_message)]

                if active == '0':
                    queryset = queryset.filter(
                        Q(
                            subject_type__in=(
                                SubjectType.DEEP_SKY,
                                SubjectType.SOLAR_SYSTEM,
                                SubjectType.WIDE_FIELD,
                                SubjectType.STAR_TRAILS,
                                SubjectType.NORTHERN_LIGHTS,
                                SubjectType.NOCTILUCENT_CLOUDS,
                                SubjectType.OTHER
                            )
                        ) &
                        Q(acquisition=None) | Q(acquisition__date=None)
                    ).distinct()
                else:
                    if active in (None, '') and distinct_years:
                        active = str(distinct_years[0])

                    if active:
                        queryset = queryset.filter(acquisition__date__year=active).order_by('-published').distinct()

        ########
        # GEAR #
        ########
        elif subsection == 'gear':
            telescopes = Telescope.objects.filter(
                images_using_for_imaging__user=self.user,
                images_using_for_imaging__deleted__isnull=True,
                images_using_for_imaging__is_wip=False,
            ).distinct()
            cameras = Camera.objects.filter(
                images_using_for_imaging__user=self.user,
                images_using_for_imaging__deleted__isnull=True,
                images_using_for_imaging__is_wip=False,
            ).distinct()

            telescopes_2 = TelescopeV2.objects.filter(
                images_using_for_imaging__user=self.user,
                images_using_for_imaging__deleted__isnull=True,
                images_using_for_imaging__is_wip=False,
            ).distinct()
            cameras_2 = CameraV2.objects.filter(
                images_using_for_imaging__user=self.user,
                images_using_for_imaging__deleted__isnull=True,
                images_using_for_imaging__is_wip=False,
            ).distinct()

            no_date_message = _("No imaging telescopes or lenses, or no imaging cameras specified")
            gear_images_message = _("Gear images")

            # L = LEGACY, N = NEW
            menu += [(f'L{x.id}', str(x)) for x in telescopes]
            menu += [(f'N{x.id}', str(x)) for x in telescopes_2]
            menu += [(f'L{x.id}', str(x)) for x in cameras]
            menu += [(f'N{x.id}', str(x)) for x in cameras_2]
            menu += [(0, no_date_message)]
            menu += [(-1, gear_images_message)]

            if active == '0':
                queryset = queryset.filter(
                    (Q(subject_type=SubjectType.DEEP_SKY) | Q(subject_type=SubjectType.SOLAR_SYSTEM)) &
                    (Q(imaging_telescopes=None) | Q(imaging_cameras=None))
                ).distinct()
            elif active == '-1':
                queryset = queryset.filter(Q(subject_type=SubjectType.GEAR)).distinct()
            else:
                if active in (None, ''):
                    if telescopes:
                        active = f'L{telescopes[0].id}'
                    elif telescopes_2:
                        active = f'N{telescopes_2[0].id}'
                    elif cameras:
                        active = f'L{cameras[0].id}'
                    elif cameras_2:
                        active = f'N{cameras_2[0].id}'

                if active:
                    if active.startswith('L'):
                        active = active.replace('L', '')
                        queryset = queryset.filter(
                            Q(imaging_telescopes__id=active) |
                            Q(imaging_cameras__id=active)
                        ).distinct()
                    elif active.startswith('N'):
                        active = active.replace('N', '')
                        if klass in (None, 'telescope'):
                            queryset = queryset.filter(imaging_telescopes_2__id=active).distinct()
                        elif klass == 'camera':
                            queryset = queryset.filter(imaging_cameras_2__id=active).distinct()
                        else:
                            queryset = queryset.none()


        ###########
        # SUBJECT #
        ###########
        elif subsection == 'subject':
            menu += [('DEEP', _("Deep sky"))]
            menu += [('SOLAR', _("Solar system"))]
            menu += [('WIDE', _("Extremely wide field"))]
            menu += [('TRAILS', _("Star trails"))]
            menu += [('NORTHERN_LIGHTS', _("Northern lights"))]
            menu += [('NOCTILUCENT_CLOUDS', _("Noctilucent clouds"))]
            menu += [('GEAR', _("Gear"))]
            menu += [('OTHER', _("Other"))]

            if active in (None, ''):
                active = 'DEEP'

            if active == 'DEEP':
                queryset = queryset.filter(subject_type=SubjectType.DEEP_SKY)

            elif active == 'SOLAR':
                queryset = queryset.filter(subject_type=SubjectType.SOLAR_SYSTEM)

            elif active == 'WIDE':
                queryset = queryset.filter(subject_type=SubjectType.WIDE_FIELD)

            elif active == 'TRAILS':
                queryset = queryset.filter(subject_type=SubjectType.STAR_TRAILS)

            elif active == 'NORTHERN_LIGHTS':
                queryset = queryset.filter(subject_type=SubjectType.NORTHERN_LIGHTS)

            elif active == 'NOCTILUCENT_CLOUDS':
                queryset = queryset.filter(subject_type=SubjectType.NOCTILUCENT_CLOUDS)

            elif active == 'GEAR':
                queryset = queryset.filter(subject_type=SubjectType.GEAR)

            elif active == 'OTHER':
                queryset = queryset.filter(subject_type=SubjectType.OTHER)

        #################
        # CONSTELLATION #
        #################
        elif subsection == 'constellation':
            queryset = queryset.filter(subject_type=SubjectType.DEEP_SKY)

            images_by_constellation = {
                'n/a': []
            }

            for image in queryset.iterator():
                image_constellation = ImageService.get_constellation(image.solution)
                if image_constellation:
                    if not images_by_constellation.get(image_constellation.get('abbreviation')):
                        images_by_constellation[image_constellation.get('abbreviation')] = []
                    images_by_constellation.get(image_constellation.get('abbreviation')).append(image)
                else:
                    images_by_constellation.get('n/a').append(image)

            menu += [('ALL', _('All'))]
            for constellation in ConstellationsService.constellation_table:
                if images_by_constellation.get(constellation[0]):
                    menu += [(
                        constellation[0],
                        constellation[1] + ' (%d)' % len(images_by_constellation.get(constellation[0]))
                    )]
            if images_by_constellation.get('n/a') and len(images_by_constellation.get('n/a')) > 0:
                menu += [('n/a', _('n/a') + ' (%d)' % len(images_by_constellation.get('n/a')))]

            if active in (None, ''):
                active = 'ALL'

            if active != 'ALL':
                try:
                    queryset = queryset.filter(pk__in=[x.pk for x in images_by_constellation[active]])
                except KeyError:
                    log.warning("Requested missing constellation %s for user %d" % (active, self.user.pk))
                    queryset = Image.objects.none()

        ###########
        # NO DATA #
        ###########
        elif subsection == 'nodata':
            menu += [('SUB', _("No subjects specified"))]
            menu += [('GEAR', _("No imaging telescopes or lenses, or no imaging cameras specified"))]
            menu += [('ACQ', _("No acquisition details specified"))]

            if active is None:
                active = 'SUB'

            if active == 'SUB':
                queryset = queryset.filter(
                    (
                            Q(subject_type=SubjectType.DEEP_SKY) |
                            Q(subject_type=SubjectType.SOLAR_SYSTEM) |
                            Q(subject_type=SubjectType.WIDE_FIELD) |
                            Q(subject_type=SubjectType.STAR_TRAILS) |
                            Q(subject_type=SubjectType.NORTHERN_LIGHTS) |
                            Q(subject_type=SubjectType.NOCTILUCENT_CLOUDS)
                    ) &
                    (Q(solar_system_main_subject=None))
                )
                queryset = [x for x in queryset if (x.solution is None or x.solution.objects_in_field is None)]
                for i in queryset:
                    for r in i.revisions.all():
                        if r.solution and r.solution.objects_in_field:
                            if i in queryset:
                                queryset.remove(i)

            elif active == 'GEAR':
                queryset = queryset.filter(
                    Q(
                        subject_type__in=(
                            SubjectType.DEEP_SKY,
                            SubjectType.SOLAR_SYSTEM,
                            SubjectType.WIDE_FIELD,
                            SubjectType.STAR_TRAILS,
                            SubjectType.NORTHERN_LIGHTS,
                            SubjectType.NOCTILUCENT_CLOUDS,
                        )
                    ) &
                    (Q(imaging_telescopes=None) | Q(imaging_cameras=None))
                )

            elif active == 'ACQ':
                queryset = queryset.filter(
                    Q(
                        subject_type__in=(
                            SubjectType.DEEP_SKY,
                            SubjectType.SOLAR_SYSTEM,
                            SubjectType.WIDE_FIELD,
                            SubjectType.STAR_TRAILS,
                            SubjectType.NORTHERN_LIGHTS,
                            SubjectType.NOCTILUCENT_CLOUDS,
                        )
                    ) &
                    Q(acquisition=None)
                )

        return queryset, menu

    def update_premium_counter_on_subscription(self, subscription: Subscription):
        from astrobin.models import Image, UserProfile

        profile: UserProfile = self.user.userprofile

        if subscription.group.name == 'astrobin_lite':
            profile.premium_counter = 0
            profile.save(keep_deleted=True)
        elif subscription.group.name == 'astrobin_lite_2020':
            profile.premium_counter = Image.objects_including_wip.filter(user=self.user).count()
            profile.save(keep_deleted=True)

    def is_in_group(self, group_name: Union[str, List[str]]) -> bool:
        if not self.user or not self.user.is_authenticated:
            return False

        if type(group_name) is list:
            return self.user.groups.filter(name__in=group_name)

        return self.user.groups.filter(name=group_name)

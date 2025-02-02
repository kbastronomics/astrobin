import logging

from annoying.functions import get_object_or_None
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q, QuerySet
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from fuzzywuzzy import fuzz
from fuzzywuzzy.utils import asciidammit
from pybb.models import Category, Forum, Topic

from astrobin_apps_equipment.models import EquipmentBrand, EquipmentBrandListing
from astrobin_apps_equipment.models.deep_sky_acquisition_migration_record import DeepSkyAcquisitionMigrationRecord
from astrobin_apps_equipment.models.equipment_item_group import EquipmentItemKlass, EquipmentItemUsageType
from astrobin_apps_notifications.utils import build_notification_url, push_notification
from common.services import AppRedirectionService

log = logging.getLogger('apps')


class EquipmentService:
    @staticmethod
    def equipment_brand_listings(brand: EquipmentBrand, country: str) -> QuerySet:
        if country is None or brand is None:
            return EquipmentBrandListing.objects.none()

        return brand.listings.filter(
            Q(retailer__countries__icontains=country) |
            Q(retailer__countries=None)
        )

    @staticmethod
    def image_has_equipment_items(image) -> bool:
        return (
                image.imaging_telescopes_2.exists() or
                image.guiding_telescopes_2.exists() or
                image.mounts_2.exists() or
                image.imaging_cameras_2.exists() or
                image.guiding_cameras_2.exists() or
                image.software_2.exists() or
                image.filters_2.exists() or
                image.accessories_2.exists()
        )

    @staticmethod
    def apply_migration_strategy(migration_strategy):
        from astrobin.models import (
            Gear, GearMigrationStrategy, Image, Telescope, Camera, Mount, Filter, FocalReducer, Accessory, Software
        )
        from astrobin.models import DeepSky_Acquisition, GearUserInfo
        from astrobin_apps_equipment.models import (
            TelescopeMigrationRecord, CameraMigrationRecord,
            MountMigrationRecord, FilterMigrationRecord, FocalReducerMigrationRecord, AccessoryMigrationRecord,
            SoftwareMigrationRecord, MigrationUsageType,
            Camera as Camera2
        )

        def _perform_apply(migration_strategy_to_apply: GearMigrationStrategy):
            if migration_strategy_to_apply.migration_flag != 'MIGRATE':
                return

            gear: Gear = migration_strategy_to_apply.gear

            for usage_data in (
                    ('imaging_telescopes', 'imaging_telescopes_2', Telescope, TelescopeMigrationRecord,
                     MigrationUsageType.IMAGING),
                    ('guiding_telescopes', 'guiding_telescopes_2', Telescope, TelescopeMigrationRecord,
                     MigrationUsageType.GUIDING),
                    ('imaging_cameras', 'imaging_cameras_2', Camera, CameraMigrationRecord, MigrationUsageType.IMAGING),
                    ('guiding_cameras', 'guiding_cameras_2', Camera, CameraMigrationRecord, MigrationUsageType.GUIDING),
                    ('mounts', 'mounts_2', Mount, MountMigrationRecord, None),
                    ('filters', 'filters_2', Filter, FilterMigrationRecord, None),
                    ('focal_reducers', 'accessories_2', FocalReducer, FocalReducerMigrationRecord, None),
                    ('accessories', 'accessories_2', Accessory, AccessoryMigrationRecord, None),
                    ('software', 'software_2', Software, SoftwareMigrationRecord, None),
            ):
                usage = usage_data[0]
                new_usage = usage_data[1]
                GearKlass = usage_data[2]
                RecordKlass = usage_data[3]
                usage_type = usage_data[4]

                try:
                    images = Image.objects_including_wip.filter(**{usage: gear}, user=migration_strategy_to_apply.user)
                except ValueError:
                    continue

                if not images.exists():
                    continue

                classed_gear = GearKlass.objects.get(pk=gear.pk)
                target = migration_strategy_to_apply.migration_content_object
                if GearKlass == Camera:
                    gear_user_info = get_object_or_None(
                        GearUserInfo,
                        gear=gear,
                        user=migration_strategy_to_apply.user,
                        modded=True,
                    )
                    if gear_user_info:
                        modified_camera = get_object_or_None(
                            Camera2,
                            brand=target.brand,
                            name=target.name,
                            modified=True,
                            cooled=False,
                        )
                        if modified_camera:
                            target = modified_camera

                for image in images.iterator():
                    try:
                        getattr(image, new_usage).add(target)
                        getattr(image, usage).remove(classed_gear)

                        params = dict(
                            image=image,
                            from_gear=classed_gear,
                            to_item=target
                        )

                        if usage_type:
                            params['usage_type'] = usage_type

                        RecordKlass.objects.get_or_create(**params)
                    except TypeError:
                        continue

            try:
                deep_sky_acquisitions = DeepSky_Acquisition.objects.filter(
                    image__user=migration_strategy_to_apply.user,
                    filter=Filter.objects.get(pk=gear.pk)
                )
                deep_sky_acquisition: DeepSky_Acquisition
                for deep_sky_acquisition in deep_sky_acquisitions.iterator():
                    deep_sky_acquisition.filter = None
                    deep_sky_acquisition.filter_2 = migration_strategy_to_apply.migration_content_object
                    deep_sky_acquisition.save()
                    if not deep_sky_acquisition.image.filters_2.filter(
                            pk=migration_strategy_to_apply.migration_content_object.pk
                    ).exists():
                        deep_sky_acquisition.image.filters_2.add(migration_strategy_to_apply.migration_content_object)
                    DeepSkyAcquisitionMigrationRecord.objects.get_or_create(
                        deep_sky_acquisition=deep_sky_acquisition,
                        from_gear=Filter.objects.get(pk=gear.pk),
                        to_item=migration_strategy_to_apply.migration_content_object
                    )
            except Filter.DoesNotExist:
                pass

            Gear.objects.filter(pk=migration_strategy_to_apply.gear.pk).update(
                migration_flag_moderator_lock=None,
                migration_flag_moderator_lock_timestamp=None
            )

            GearMigrationStrategy.objects.filter(pk=migration_strategy_to_apply.pk).update(applied=timezone.now())

        migration_strategy: GearMigrationStrategy = migration_strategy
        if migration_strategy.user:
            _perform_apply(migration_strategy)
        else:
            migration_strategies: QuerySet = GearMigrationStrategy.objects.filter(
                user__isnull=False,
                gear=migration_strategy.gear,
                migration_flag_moderator=migration_strategy.migration_flag_moderator
            )
            for x in migration_strategies:
                _perform_apply(x)

    @staticmethod
    def undo_migration_strategy(migration_strategy):
        from astrobin.models import (
            Gear, GearMigrationStrategy, DeepSky_Acquisition, Telescope as LegacyTelescope, Camera as LegacyCamera,
            Mount as LegacyMount, Filter as LegacyFilter, Accessory as LegacyAccessory, Software as LegacySoftware,
            FocalReducer
        )
        from astrobin_apps_equipment.models import (
            AccessoryMigrationRecord, CameraMigrationRecord, FilterMigrationRecord, MigrationUsageType,
            MountMigrationRecord, SoftwareMigrationRecord, TelescopeMigrationRecord, FocalReducerMigrationRecord,
        )

        def _perform_undo(migration_strategy_to_undo):
            if migration_strategy_to_undo.migration_flag == 'MIGRATE':
                for RecordClass in (
                        (TelescopeMigrationRecord, 'telescopes', LegacyTelescope),
                        (CameraMigrationRecord, 'cameras', LegacyCamera),
                        (MountMigrationRecord, 'mounts', LegacyMount),
                        (FilterMigrationRecord, 'filters', LegacyFilter),
                        (AccessoryMigrationRecord, 'accessories', LegacyAccessory),
                        (SoftwareMigrationRecord, 'software', LegacySoftware),
                ):
                    try:
                        records = RecordClass[0].objects.filter(
                            from_gear=migration_strategy_to_undo.gear, image__user=migration_strategy_to_undo.user
                        )
                    except ValueError:
                        continue

                    record: RecordClass[0]
                    for record in records:
                        legacy_item = RecordClass[2].objects.get(pk=migration_strategy_to_undo.gear.pk)
                        if hasattr(record, 'usage_type'):
                            if record.usage_type == MigrationUsageType.IMAGING:
                                getattr(record.image, f'imaging_{RecordClass[1]}_2').remove(
                                    migration_strategy_to_undo.migration_content_object
                                )
                                getattr(record.image, f'imaging_{RecordClass[1]}').add(
                                    legacy_item
                                )
                            elif record.usage_type == MigrationUsageType.GUIDING:
                                getattr(record.image, f'guiding_{RecordClass[1]}_2').remove(
                                    migration_strategy_to_undo.migration_content_object
                                )
                                getattr(record.image, f'guiding_{RecordClass[1]}').add(
                                    legacy_item
                                )
                        else:
                            getattr(record.image, f'{RecordClass[1]}_2').remove(
                                migration_strategy_to_undo.migration_content_object
                            )
                            getattr(record.image, f'{RecordClass[1]}').add(
                                legacy_item
                            )

                    records.delete()

                # Handle focal reducers separately because they are Accessories in the new equipment database.
                try:
                    records = FocalReducerMigrationRecord.objects.filter(
                        from_gear=migration_strategy_to_undo.gear, image__user=migration_strategy_to_undo.user
                    )

                    for record in records:
                        legacy_item = FocalReducer.objects.get(pk=migration_strategy_to_undo.gear.pk)
                        getattr(record.image, 'accessories_2').remove(migration_strategy_to_undo.migration_content_object)
                        getattr(record.image, 'focal_reducers').add(legacy_item)

                    records.delete()
                except ValueError:
                    pass

                try:
                    legacy_filter: LegacyFilter = LegacyFilter.objects.get(pk=migration_strategy_to_undo.gear.pk)
                    for deep_sky_acquisition_migration_record in DeepSkyAcquisitionMigrationRecord.objects.filter(
                            deep_sky_acquisition__image__user=migration_strategy_to_undo.user,
                            from_gear=legacy_filter,
                            to_item=migration_strategy_to_undo.migration_content_object
                    ):
                        deep_sky_acquisition: DeepSky_Acquisition = deep_sky_acquisition_migration_record.deep_sky_acquisition
                        deep_sky_acquisition.filter = legacy_filter
                        deep_sky_acquisition.filter_2 = None
                        deep_sky_acquisition.save()
                        if not deep_sky_acquisition.image.filters_2.filter(pk=legacy_filter.pk).exists():
                            deep_sky_acquisition.image.filters.add(legacy_filter)
                        deep_sky_acquisition_migration_record.delete()
                except LegacyFilter.DoesNotExist:
                    pass

            Gear.objects.filter(pk=migration_strategy_to_undo.gear.pk).update(
                migration_flag_moderator_lock=None,
                migration_flag_moderator_lock_timestamp=None
            )

            migration_strategy_to_undo.delete()

        migration_strategy: GearMigrationStrategy = migration_strategy
        if migration_strategy.user:
            _perform_undo(migration_strategy)
        else:
            migration_strategies: QuerySet = GearMigrationStrategy.objects.filter(
                user__isnull=False,
                gear=migration_strategy.gear,
                migration_flag_moderator=migration_strategy.migration_flag_moderator
            )

            for x in migration_strategies:
                _perform_undo(x)

            migration_strategy.delete()

    @staticmethod
    def reject_item(item):
        from astrobin_apps_equipment.models import Sensor
        from astrobin_apps_equipment.models import Camera
        from astrobin_apps_equipment.models.camera_base_model import CameraType
        from astrobin_apps_equipment.models import CameraEditProposal
        from astrobin_apps_equipment.models import Telescope
        from astrobin_apps_equipment.models import Mount
        from astrobin_apps_equipment.models import Filter
        from astrobin_apps_equipment.models import Accessory
        from astrobin_apps_equipment.models import Software
        from astrobin.models import GearMigrationStrategy, Image

        reviewer = item.reviewed_by

        duplicate_of = None
        DuplicateModelClass = {
            EquipmentItemKlass.SENSOR: Sensor,
            EquipmentItemKlass.TELESCOPE: Telescope,
            EquipmentItemKlass.CAMERA: Camera,
            EquipmentItemKlass.MOUNT: Mount,
            EquipmentItemKlass.FILTER: Filter,
            EquipmentItemKlass.ACCESSORY: Accessory,
            EquipmentItemKlass.SOFTWARE: Software
        }.get(item.reviewer_rejection_duplicate_of_klass)

        ModelClass = type(item)

        log.debug(f'reject_item: going to reject {item.klass}/{item.id}')

        if item.reviewer_rejection_duplicate_of:
            try:
                duplicate_of = DuplicateModelClass.objects.get(pk=item.reviewer_rejection_duplicate_of)
            except ModelClass.DoesNotExist:
                log.warning(
                    f'reject_item: duplicate {item.reviewer_rejection_duplicate_of_klass}/'
                    f'{item.reviewer_rejection_duplicate_of} or {item.klass}/{item.id} does not exist')
                duplicate_of = None
                item.reviewer_rejection_duplicate_of = None
                item.reviewer_rejection_duplicate_of_klass = None
                item.reviewer_rejection_duplicate_of_klass_usage_type = None

        if item.created_by and item.created_by != reviewer:
            push_notification(
                [item.created_by],
                reviewer,
                'equipment-item-rejected',
                {
                    'user': reviewer.userprofile.get_display_name(),
                    'user_url': build_notification_url(
                        settings.BASE_URL + reverse('user_page', args=(reviewer.username,))
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
            migration_content_type=ContentType.objects.get_for_model(ModelClass),
            migration_object_id=item.id,
        )

        log.debug(f'reject_item: found {migration_strategies.count()} migration strategies for {item.klass}/{item.id}')

        if duplicate_of:
            migration_strategies.update(
                migration_object_id=duplicate_of.pk,
                migration_content_type=ContentType.objects.get_for_model(DuplicateModelClass)
            )

            category, created = Category.objects.get_or_create(
                name='Equipment forums',
                slug='equipment-forums',
            )

            duplicate_of.forum, created = Forum.objects.get_or_create(
                category=category,
                name=f'{duplicate_of}',
            )

            Topic.objects.filter(forum=item.forum).update(forum=duplicate_of.forum)
        else:
            for migration_strategy in migration_strategies:
                log.debug(f'reject_item: undoing migration strategy {migration_strategy.id} for {item.klass}/{item.id}')
                EquipmentService.undo_migration_strategy(migration_strategy)

        # This will catch DSLR/Mirrorless variants
        affected_items = ModelClass.objects.filter(brand=item.brand, name=item.name)
        for affected_item in affected_items.iterator():
            log.debug(f'reject_item: processing affected item {affected_item.id} for {item.klass}/{item.id}')
            replace_with: DuplicateModelClass = duplicate_of

            if (
                    duplicate_of and
                    affected_item.klass == EquipmentItemKlass.CAMERA and
                    affected_item.type == CameraType.DSLR_MIRRORLESS and
                    duplicate_of.klass == EquipmentItemKlass.CAMERA and
                    duplicate_of.type == CameraType.DSLR_MIRRORLESS
            ):
                # Try and fetch the corresponding modified/cooled target of duplication
                try:
                    replace_with = Camera.objects.get(
                        brand=duplicate_of.brand,
                        name=duplicate_of.name,
                        modified=affected_item.modified,
                        cooled=affected_item.cooled,
                    )
                except Camera.DoesNotExist:
                    replace_with = duplicate_of

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
                    images = Image.objects_including_wip.filter(**{prop: affected_item})
                except ValueError:
                    images = None

                if images is not None and images.count() > 0:
                    for image in images.iterator():
                        affected_images.append(dict(image=image, prop=prop))

            for affected in affected_images:
                image: Image = affected.get("image")
                prop: str = affected.get("prop")

                log.debug(f'reject_item: processing affected image {image.id} for {item.klass}/{item.id}')

                if duplicate_of:
                    log.debug(
                        f'reject_item: adding duplicate item to affected image {image.id} for {item.klass}/{item.id}'
                    )
                    if ModelClass == DuplicateModelClass:
                        getattr(image, prop).add(replace_with)
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
                        getattr(image, destination_map.get(duplicate_of.klass)).add(replace_with)

                push_notification(
                    [image.user],
                    reviewer,
                    'equipment-item-rejected-affected-image',
                    {
                        'user': reviewer.userprofile.get_display_name(),
                        'user_url': build_notification_url(
                            settings.BASE_URL + reverse('user_page', args=(reviewer.username,))
                        ),
                        'item': str(item),
                        'reject_reason': item.reviewer_rejection_reason,
                        'comment': item.reviewer_comment,
                        'duplicate_of': replace_with,
                        'duplicate_of_url': build_notification_url(
                            AppRedirectionService.redirect(
                                f'/equipment'
                                f'/explorer'
                                f'/{replace_with.item_type}/{replace_with.pk}'
                                f'/{replace_with.slug}'
                            )
                        ) if duplicate_of else None,
                        'image_url': build_notification_url(
                            settings.BASE_URL + reverse('image_detail', args=(image.get_id(),))
                        ),
                        'image_title': image.title,
                    }
                )

        if item.klass == EquipmentItemKlass.SENSOR:
            log.debug(f'reject_item: removing rejected sensor from cameras for {item.klass}/{item.id}')
            Camera.all_objects.filter(sensor=item).update(sensor=None)
            CameraEditProposal.all_objects.filter(sensor=item).update(sensor=None)

        log.debug(f'reject_item: deleting item {item.klass}/{item.id}')
        item.delete()

        if item.brand:
            brand_has_items = False
            for klass in (Sensor, Camera, Telescope, Mount, Filter, Accessory, Software):
                if klass.objects.filter(brand=item.brand).exists():
                    brand_has_items = True
                    break

            if not brand_has_items:
                log.debug(f'reject_item: deleting brand for item {item.klass}/{item.id}')
                item.brand.delete()

        return item

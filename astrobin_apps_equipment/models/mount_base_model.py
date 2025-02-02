from django.db import models
from django.utils.translation import ugettext_lazy as _

from astrobin_apps_equipment.models import EquipmentItem
from astrobin_apps_equipment.models.equipment_item_group import EquipmentItemKlass


class MountType:
    ALTAZIMUTH = 'ALTAZIMUTH'
    WEDGED_ALTAZIMUTH = 'WEDGED_ALTAZIMUTH'
    EQUATORIAL = 'EQUATORIAL'
    GERMAN_EQUATORIAL = 'GERMAN_EQUATORIAL'
    FORK = 'FORK'
    DOBSONIAN = 'DOBSONIAN'
    PORTABLE_ENGLISH = 'PORTABLE_ENGLISH'
    STAR_TRACKER = 'STAR_TRACKER'
    ALT_ALT = 'ALT_ALT'
    TRANSIT = 'TRANSIT'
    HEXAPOD = 'HEXAPOD'
    DUAL_ALT_AZ_EQ = 'DUAL_ALT_AZ_EQ'
    TRIPOD = 'TRIPOD'
    OTHER = 'OTHER'


class MountBaseModel(EquipmentItem):
    MOUNT_TYPES = (
        (MountType.ALTAZIMUTH, _("Alt-Az (altazimuth)")),
        (MountType.WEDGED_ALTAZIMUTH, _("Wedged Alt-Az")),
        (MountType.EQUATORIAL, _("Equatorial")),
        (MountType.GERMAN_EQUATORIAL, _("German equatorial")),
        (MountType.FORK, _("Fork")),
        (MountType.DOBSONIAN, _("Dobsonian")),
        (MountType.PORTABLE_ENGLISH, _("Portable English")),
        (MountType.STAR_TRACKER, _("Star tracker")),
        (MountType.ALT_ALT, _("Alt-Alt (altitude-altitude)")),
        (MountType.TRANSIT, _("Transit")),
        (MountType.HEXAPOD, _("Hexapod")),
        (MountType.TRIPOD, _("Tripod")),
        (MountType.DUAL_ALT_AZ_EQ, _("Dual Alt-Az / Equatorial")),
        (MountType.OTHER, _("Other")),
    )

    type = models.CharField(
        verbose_name=_('Type'),
        null=False,
        max_length=32,
        choices=MOUNT_TYPES,
    )

    weight = models.DecimalField(
        verbose_name=_("Weight (kg)"),
        null=True,
        blank=True,
        max_digits=6,
        decimal_places=2
    )

    max_payload = models.DecimalField(
        verbose_name=_("Payload (kg)"),
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )

    computerized = models.BooleanField(
        verbose_name=_("Computerized"),
        null=True,
        blank=True,
    )

    periodic_error = models.DecimalField(
        verbose_name=_("Periodic error (arcsec)"),
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )

    pec = models.BooleanField(
        verbose_name=_("Periodic error correction"),
        null=True,
        blank=True,
    )

    slew_speed = models.DecimalField(
        verbose_name=_("Slew speed (deg/sec)"),
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
    )

    def type_label(self):
        if self.type is not None:
            for i in self.MOUNT_TYPES:
                if self.type == i[0]:
                    return i[1]

        return _("Unknown")

    def properties(self):
        properties = []

        for item_property in (
                'type', 'weight', 'max_payload', 'computerized', 'periodic_error', 'pec', 'slew_speed'
        ):
            property_label = self._meta.get_field(item_property).verbose_name
            if item_property == 'type':
                property_value = self.type_label()
            else:
                property_value = getattr(self, item_property)

            if property_value is not None:
                if property_value is not None:
                    if property_value.__class__.__name__ == 'Decimal':
                        property_value = '%g' % property_value
                properties.append({'label': property_label, 'value': property_value})

        return properties

    def save(self, keep_deleted=False, **kwargs):
        self.klass = EquipmentItemKlass.MOUNT
        super().save(keep_deleted, **kwargs)

    class Meta(EquipmentItem.Meta):
        abstract = True

from django.db import models

from astrobin_apps_equipment.models import Sensor
from astrobin_apps_equipment.models.equipment_item_edit_proposal_mixin import EquipmentItemEditProposalMixin
from astrobin_apps_equipment.models.sensor_base_model import SensorBaseModel


class SensorEditProposal(SensorBaseModel, EquipmentItemEditProposalMixin):
    edit_proposal_target = models.ForeignKey(Sensor, on_delete=models.CASCADE, related_name="edit_proposals")

    # We need to override this, lest 'self' refers to the *EditProposal model instead of the actual model
    variant_of = models.ForeignKey(
        Sensor,
        null=True,
        blank=True,
        related_name='variants_in_edit_proposals',
        on_delete=models.SET_NULL
    )

    def get_absolute_url(self):
        return self.get_absolute_url_base('sensor')

    class Meta(SensorBaseModel.Meta):
        unique_together = []
        ordering = ['-edit_proposal_created']
        abstract = False

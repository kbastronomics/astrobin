from django.db import models

from astrobin_apps_equipment.models import Software
from astrobin_apps_equipment.models.software_base_model import SoftwareBaseModel
from astrobin_apps_equipment.models.equipment_item_edit_proposal_mixin import EquipmentItemEditProposalMixin


class SoftwareEditProposal(SoftwareBaseModel, EquipmentItemEditProposalMixin):
    edit_proposal_target = models.ForeignKey(Software, on_delete=models.CASCADE, related_name="edit_proposals")

    # We need to override this, lest 'self' refers to the *EditProposal model instead of the actual model
    variant_of = models.ForeignKey(
        Software,
        null=True,
        blank=True,
        related_name='variants_in_edit_proposals',
        on_delete=models.SET_NULL
    )

    def get_absolute_url(self):
        return self.get_absolute_url_base('software')

    class Meta(SoftwareBaseModel.Meta):
        unique_together = []
        ordering = ['-edit_proposal_created']
        abstract = False

from django.contrib.auth.models import User
from django.db import models
from django.db.models import SET_NULL, PROTECT
from django.utils.text import slugify
from django.utils.translation import ugettext_lazy as _
from pybb.models import Forum
from safedelete.models import SafeDeleteModel

from astrobin_apps_equipment.models import EquipmentBrand
from astrobin_apps_equipment.models.equipment_item_group import (
    EQUIPMENT_ITEM_USAGE_TYPE_CHOICES, EquipmentItemGroup,
    EQUIPMENT_ITEM_KLASS_CHOICES,
)
from astrobin_apps_equipment.services.equipment_item_service import EquipmentItemService
from common.services import AppRedirectionService
from common.upload_paths import upload_path


def image_upload_path(instance, filename):
    return upload_path('equipment_item_images', instance.created_by.pk if instance.created_by else 0, filename)


class EquipmentItemReviewerDecision:
    APPROVED = 'APPROVED'
    REJECTED = 'REJECTED'


class EquipmentItem(SafeDeleteModel):
    klass = models.CharField(
        max_length=16,
        null=True,
        blank=False,
        choices=EQUIPMENT_ITEM_KLASS_CHOICES
    )

    variant_of = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        related_name='variants',
        on_delete=models.SET_NULL
    )

    created_by = models.ForeignKey(
        User,
        related_name='%(app_label)s_%(class)ss_created',
        on_delete=SET_NULL,
        null=True,
        editable=False,
    )

    assignee = models.ForeignKey(
        User,
        on_delete=SET_NULL,
        related_name='%(app_label)s_%(class)ss_assigned_for_review',
        null=True,
        blank=True
    )

    reviewer_lock = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='%(app_label)s_%(class)s_reviewer_locks',
    )

    reviewer_lock_timestamp = models.DateTimeField(
        null=True,
        blank=True,
    )

    reviewed_by = models.ForeignKey(
        User,
        related_name='%(app_label)s_%(class)ss_reviewed',
        on_delete=SET_NULL,
        null=True,
        editable=False,
    )

    reviewed_timestamp = models.DateTimeField(
        auto_now=False,
        null=True,
        editable=False,
    )

    reviewer_decision = models.CharField(
        max_length=8,
        choices=[
            (EquipmentItemReviewerDecision.APPROVED, _('Approved')),
            (EquipmentItemReviewerDecision.REJECTED, _('Rejected')),
        ],
        null=True,
        editable=False,
    )

    reviewer_rejection_reason = models.CharField(
        max_length=32,
        choices=[
            ('TYPO', 'There\'s a typo in the name of the item'),
            ('WRONG_BRAND', 'The item was assigned to the wrong brand'),
            ('INACCURATE_DATA', 'Some data is inaccurate'),
            ('INSUFFICIENT_DATA', 'Some important data is missing'),
            ('DUPLICATE', 'This item already exists in the database'),
            ('OTHER', _('Other'))
        ],
        null=True,
        editable=False,
    )

    reviewer_rejection_duplicate_of_klass = models.CharField(
        max_length=16,
        null=True,
        blank=True,
        choices=EQUIPMENT_ITEM_KLASS_CHOICES
    )

    reviewer_rejection_duplicate_of_usage_type = models.CharField(
        max_length=16,
        null=True,
        blank=True,
        choices=EQUIPMENT_ITEM_USAGE_TYPE_CHOICES
    )

    reviewer_rejection_duplicate_of = models.PositiveIntegerField(
        null=True,
        blank=True,
        editable=False,
    )

    reviewer_comment = models.TextField(
        null=True,
        editable=False,
    )

    created = models.DateTimeField(
        auto_now_add=True,
        null=False,
        editable=False
    )

    updated = models.DateTimeField(
        auto_now=True,
        null=False,
        editable=False
    )

    last_added_or_removed_from_image = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
    )

    edit_proposal_lock = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='%(app_label)s_%(class)s_edit_proposal_locks',
    )

    edit_proposal_lock_timestamp = models.DateTimeField(
        null=True,
        blank=True,
    )

    brand = models.ForeignKey(
        EquipmentBrand,
        related_name='%(app_label)s_brand_%(class)ss',
        on_delete=PROTECT,
        null=True,
        blank=True,
    )

    name = models.CharField(
        max_length=128,
        null=False,
        blank=False,
    )

    search_friendly_name = models.CharField(
        max_length=256,
        null=False,
        blank=False,
        editable=False,
    )

    community_notes = models.TextField(
        null=True,
        blank=True,
    )

    website = models.URLField(
        blank=True,
        null=True,
    )

    image = models.ImageField(
        upload_to=image_upload_path,
        null=True,
        blank=True,
    )

    group = models.ForeignKey(
        EquipmentItemGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    frozen_as_ambiguous = models.BooleanField(
        null=True,
        blank=True,
    )

    forum = models.OneToOneField(
        Forum,
        null=True,
        blank=True,
        editable=False,
        related_name='%(app_label)s_%(class)s_equipment_item',
        on_delete=models.SET_NULL
    )
    ####################################################################################################################
    # This items are synced back from the search index.                                                                #
    ####################################################################################################################

    user_count = models.PositiveIntegerField(
        editable=False,
        default=0
    )

    image_count = models.PositiveIntegerField(
        editable=False,
        default=0
    )

    ####################################################################################################################
    ####################################################################################################################

    @property
    def item_type(self):
        return EquipmentItemService(self).get_type()

    @property
    def item_type_label(self):
        return EquipmentItemService(self).get_type_label()

    @property
    def slug(self):
        return slugify(f'{self.brand.name if self.brand else "diy"} {self.name}').replace('_', '-')

    def __str__(self):
        if not self.brand:
            return f'{_("DIY")} {self.name}'

        if self.brand.name == 'Unspecified/unknown company':
            return self.name

        if self.brand.name == self.name:
            return self.name

        return f'{self.brand.name} {self.name}'

    def get_absolute_url(self):
        return AppRedirectionService.redirect(f'/equipment/explorer/{self.klass.lower()}/{self.pk}')

    class Meta:
        abstract = True
        ordering = [
            'brand__name',
            'name'
        ]
        unique_together = [
            'brand',
            'name'
        ]

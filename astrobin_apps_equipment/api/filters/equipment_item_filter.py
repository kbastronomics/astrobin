import django_filters
from django.db.models import Q, QuerySet
from django_filters.rest_framework import FilterSet

from astrobin_apps_equipment.models.equipment_item import EquipmentItemReviewerDecision
from astrobin_apps_users.services import UserService
from common.constants import GroupName


class EquipmentItemFilter(FilterSet):
    pending_review = django_filters.BooleanFilter(method='has_pending_review')
    pending_edit = django_filters.BooleanFilter(method='has_pending_edit_proposals')

    def has_pending_review(self, queryset: QuerySet, value, *args, **kwargs):
        condition = args[0]

        is_authenticated: bool = self.request.user.is_authenticated
        is_moderator: bool = UserService(self.request.user).is_in_group(GroupName.EQUIPMENT_MODERATORS)

        if not is_authenticated or not is_moderator:
            return queryset.none()

        queryset = queryset.exclude(Q(created_by=self.request.user))

        if condition:
            queryset = queryset.filter(reviewer_decision__isnull=True).order_by('-created')

        return queryset

    def has_pending_edit_proposals(self, queryset: QuerySet, value, *args, **kwargs):
        condition = args[0]

        if condition:
            queryset = queryset.filter(edit_proposals__gt=0)
        else:
            queryset = queryset.exclude(edit_proposals__gt=0)

        queryset = queryset.filter(
            edit_proposals__deleted__isnull=True,
            edit_proposals__edit_proposal_review_status__isnull=True,
            reviewer_decision=EquipmentItemReviewerDecision.APPROVED,
        )

        if self.request.user.is_authenticated:
            queryset = queryset.exclude(edit_proposals__edit_proposal_by=self.request.user)

        return queryset.distinct().order_by('-created')

    class Meta:
        abstract = True
        fields = ['brand', 'name', 'pending_review', 'pending_edit']

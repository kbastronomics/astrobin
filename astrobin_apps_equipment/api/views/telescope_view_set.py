import simplejson
from django.db.models import QuerySet
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser

from astrobin_apps_equipment.api.filters.telescope_filter import TelescopeFilter
from astrobin_apps_equipment.api.serializers.telescope_image_serializer import TelescopeImageSerializer
from astrobin_apps_equipment.api.serializers.telescope_serializer import TelescopeSerializer
from astrobin_apps_equipment.api.views.equipment_item_view_set import EquipmentItemViewSet


class TelescopeViewSet(EquipmentItemViewSet):
    serializer_class = TelescopeSerializer
    filter_class = TelescopeFilter

    def get_queryset(self) -> QuerySet:
        queryset = super().get_queryset()

        telescope_type_filter = self.request.GET.get('telescope-type')
        if telescope_type_filter and telescope_type_filter != 'null':
            queryset = queryset.filter(
                type=telescope_type_filter,
            )

        telescope_aperture_filter = self.request.GET.get('telescope-aperture')
        if telescope_aperture_filter:
            aperture_object = simplejson.loads(telescope_aperture_filter)
            queryset = queryset.filter(
                aperture__isnull=False,
                aperture__gte=aperture_object.get('from'),
                aperture__lte=aperture_object.get('to')
            )

        telescope_focal_length_filter = self.request.GET.get('telescope-focal-length')
        if telescope_focal_length_filter:
            focal_length_object = simplejson.loads(telescope_focal_length_filter)
            queryset = queryset.filter(
                min_focal_length__isnull=False,
                max_focal_length__isnull=False,
                min_focal_length__gte=focal_length_object.get('from'),
                max_focal_length__lte=focal_length_object.get('to')
            )

        telescope_weight_filter = self.request.GET.get('telescope-weight')
        if telescope_weight_filter:
            weight_object = simplejson.loads(telescope_weight_filter)
            queryset = queryset.filter(
                weight__isnull=False,
                weight__gte=weight_object.get('from'),
                weight__lte=weight_object.get('to')
            )
            
        return queryset
    
    @action(
        detail=True,
        methods=['post'],
        serializer_class=TelescopeImageSerializer,
        parser_classes=[MultiPartParser, FormParser],
    )
    def image(self, request, pk):
        return super(TelescopeViewSet, self).image_upload(request, pk)

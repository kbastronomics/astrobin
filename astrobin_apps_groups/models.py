from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import ugettext_lazy as _
from pybb.models import Forum, Category

from common.utils import get_sentinel_user


class GroupCategory:
    PROFESSIONAL_NETWORK = 'PROFESSIONAL_NETWORK'
    CLUB_OR_ASSOCIATION = 'CLUB_OR_ASSOCIATION'
    INTERNET_COMMUNITY = 'INTERNET_COMMUNITY'
    FRIENDS_OR_PARTNERS = 'FRIENDS_OR_PARTNERS'
    GEOGRAPHICAL_AREA = 'GEOGRAPHICAL_AREA'
    AD_HOC_COLLABORATION = 'AD_HOC_COLLABORATION'
    SPECIFIC_TO_TECHNIQUE = 'SPECIFIC_TO_TECHNIQUE'
    SPECIFIC_TO_TARGET = 'SPECIFIC_TO_TARGET'
    SPECIFIC_TO_EQUIPMENT = 'SPECIFIC_TO_EQUIPMENT'
    OTHER = 'OTHER'


class GroupImageSorting:
    PUBLICATION = "PUBLICATION"
    TITLE = "TITLE"
    TAG = "TAG"


class Group(models.Model):
    GROUP_CATEGORY_CHOICES = (
        (GroupCategory.PROFESSIONAL_NETWORK, _("Professional network")),
        (GroupCategory.CLUB_OR_ASSOCIATION, _("Club or association")),
        (GroupCategory.INTERNET_COMMUNITY, _("Internet community")),
        (GroupCategory.FRIENDS_OR_PARTNERS, _("Friends or partners")),
        (GroupCategory.GEOGRAPHICAL_AREA, _("Geographical area")),
        (GroupCategory.AD_HOC_COLLABORATION, _("Ad-hoc collaboration")),
        (GroupCategory.SPECIFIC_TO_TECHNIQUE, _("Specific to an imaging technique")),
        (GroupCategory.SPECIFIC_TO_TARGET, _("Specific to an astrophotography target")),
        (GroupCategory.SPECIFIC_TO_EQUIPMENT, _("Specific to certain equipment")),
        (GroupCategory.OTHER, _("Other")),
    )

    GROUP_IMAGE_SORTING_CHOICES = (
        (GroupImageSorting.PUBLICATION, _("Publication")),
        (GroupImageSorting.TITLE, _("Title")),
        (GroupImageSorting.TAG, _("Key/value tag")),
    )

    date_created = models.DateTimeField(
        null=False,
        blank=False,
        auto_now_add=True,
        editable=False,
    )

    date_updated = models.DateTimeField(
        null=False,
        blank=False,
        auto_now=True,
        editable=False,
    )

    creator = models.ForeignKey(
        User,
        null=False,
        blank=False,
        editable=False,
        related_name='created_group_set',
        on_delete=models.SET(get_sentinel_user)
    )

    owner = models.ForeignKey(
        User,
        null=False,
        blank=False,
        related_name='owned_group_set',
        on_delete=models.SET(get_sentinel_user)
    )

    name = models.CharField(
        max_length=512,
        null=False,
        blank=False,
        unique=True,
        verbose_name=_("Name"),
    )

    description = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("Description"),
        help_text=_("HTML tags are allowed."),
    )

    category = models.CharField(
        max_length=100,
        choices=GROUP_CATEGORY_CHOICES,
        null=False,
        blank=False,
        verbose_name=_("Category"),
    )

    default_image_sorting = models.CharField(
        max_length=16,
        choices=GROUP_IMAGE_SORTING_CHOICES,
        default=GroupImageSorting.PUBLICATION,
        null=False,
        blank=False,
        verbose_name=_("Default image sorting"),
    )

    image_tag_sorting = models.CharField(
        max_length=16,
        null=True,
        blank=True,
        verbose_name=_("Image key/value tag sorting"),
        help_text=_(
            "If images are sorted by a key/value tag, please specify which one. "
            "<a target='_blank' href='https://welcome.astrobin.com/features/groups'>Learn more.</a>"
        )
    )

    public = models.BooleanField(
        default=False,
        verbose_name=_("Public group"),
        help_text=_("Public groups can be searched by anyone, and all their content is public."),
    )

    moderated = models.BooleanField(
        default=False,
        verbose_name=_("Moderated group"),
        help_text=_("Moderated groups have a moderation queue for posted images and join requests."),
    )

    autosubmission = models.BooleanField(
        default=False,
        verbose_name=_("Automatic submission"),
        help_text=_(
            "Groups with automatic submissions always contain all public images from all members. Groups without automatic submission only contain images that are explicitly submitted to it."),
    )

    moderators = models.ManyToManyField(
        User,
        related_name='moderated_group_set',
        blank=True,
    )

    members = models.ManyToManyField(
        User,
        related_name='joined_group_set',
        blank=True,
    )

    invited_users = models.ManyToManyField(
        User,
        related_name='invited_group_set',
        blank=True,
    )

    join_requests = models.ManyToManyField(
        User,
        related_name='join_requested_group_set',
        blank=True,
    )

    images = models.ManyToManyField(
        'astrobin.Image',
        related_name='part_of_group_set',
        blank=True,
    )

    forum = models.OneToOneField(
        Forum,
        null=True,
        blank=True,
        editable=False,
        related_name='group',
        on_delete=models.SET_NULL
    )

    @property
    def slug(self):
        return slugify(self.name)

    @property
    def members_count(self):
        return self.members.count()

    @property
    def images_count(self):
        return self.images.count()

    def category_humanized(self):
        for cat in self.GROUP_CATEGORY_CHOICES:
            if self.category == cat[0]:
                return cat[1]
        return ""

    def save(self, *args, **kwargs):
        if self.pk is None:
            category, created = Category.objects.get_or_create(
                name='Group forums',
                slug='group-forums',
            )

            self.forum, created = Forum.objects.get_or_create(
                category=category,
                name=self.name,
            )

        super(Group, self).save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('group_detail', kwargs={'pk': self.pk, 'slug': self.slug})

    def __str__(self):
        return self.name

    class Meta:
        app_label = 'astrobin_apps_groups'
        ordering = ['date_updated']

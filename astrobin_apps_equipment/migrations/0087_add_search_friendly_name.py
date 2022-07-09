# Generated by Django 2.2.24 on 2022-07-09 09:39

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('astrobin_apps_equipment', '0086_make_user_and_image_count_non_small_positive_integer_field'),
    ]

    operations = [
        migrations.AddField(
            model_name='accessory',
            name='search_friendly_name',
            field=models.CharField(default='', editable=False, max_length=256),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='accessoryeditproposal',
            name='search_friendly_name',
            field=models.CharField(default='', editable=False, max_length=256),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='camera',
            name='search_friendly_name',
            field=models.CharField(default='', editable=False, max_length=256),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='cameraeditproposal',
            name='search_friendly_name',
            field=models.CharField(default='', editable=False, max_length=256),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='filter',
            name='search_friendly_name',
            field=models.CharField(default='', editable=False, max_length=256),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='filtereditproposal',
            name='search_friendly_name',
            field=models.CharField(default='', editable=False, max_length=256),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='mount',
            name='search_friendly_name',
            field=models.CharField(default='', editable=False, max_length=256),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='mounteditproposal',
            name='search_friendly_name',
            field=models.CharField(default='', editable=False, max_length=256),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='sensor',
            name='search_friendly_name',
            field=models.CharField(default='', editable=False, max_length=256),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='sensoreditproposal',
            name='search_friendly_name',
            field=models.CharField(default='', editable=False, max_length=256),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='software',
            name='search_friendly_name',
            field=models.CharField(default='', editable=False, max_length=256),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='softwareeditproposal',
            name='search_friendly_name',
            field=models.CharField(default='', editable=False, max_length=256),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='telescope',
            name='search_friendly_name',
            field=models.CharField(default='', editable=False, max_length=256),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='telescopeeditproposal',
            name='search_friendly_name',
            field=models.CharField(default='', editable=False, max_length=256),
            preserve_default=False,
        ),
    ]

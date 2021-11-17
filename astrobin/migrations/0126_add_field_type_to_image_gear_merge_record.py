# Generated by Django 2.2.24 on 2021-11-17 17:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('astrobin', '0125_imagerevision_add_title'),
    ]

    operations = [
        migrations.AddField(
            model_name='imagegearmergerecord',
            name='type',
            field=models.CharField(
                choices=[
                    ('imaging_telescope', 'Imaging telescope'),
                    ('guiding_telescope', 'Guiding telescope'),
                    ('imaging_camera', 'Imaging camera'),
                    ('guiding_camera', 'Guiding camera'),
                    ('filter', 'Filter'),
                    ('focal_reducer', 'Focal reducer'),
                    ('mount', 'Mount'),
                    ('accessory', 'Accessory'),
                    ('software', 'Software')
                ],
                default='imaging_cameras',
                max_length=17),
            preserve_default=False,
        ),
    ]

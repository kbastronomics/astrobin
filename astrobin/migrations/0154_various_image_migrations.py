# Generated by Django 2.2.24 on 2022-06-03 11:46

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('astrobin', '0153_alter_datadownloadrequest_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='image',
            name='acquisition_type',
            field=models.CharField(
                choices=[
                    ('REGULAR', 'Regular (e.g. medium/long exposure with a CCD or DSLR)'),
                    ('EAA', 'Electronically-Assisted Astronomy (EAA, e.g. based on a live video feed)'),
                    ('LUCKY', 'Lucky imaging'),
                    ('DRAWING', 'Drawing/Sketch'),
                    ('OTHER', 'Other/Unknown')
                ],
                default='REGULAR',
                max_length=32,
                verbose_name='Acquisition type'
            ),
        ),
        migrations.AlterField(
            model_name='image',
            name='full_size_display_limitation',
            field=models.CharField(
                blank=True,
                choices=[
                    ('EVERYBODY', 'Everybody'),
                    ('PAYING', 'Paying members only'),
                    ('MEMBERS', 'Members only'),
                    ('ME', 'Me only'),
                    ('NOBODY', 'Nobody')
                ],
                default='EVERYBODY',
                help_text='Specify what user groups are allowed to view this image at its full size.',
                max_length=16,
                null=True,
                verbose_name='Allow full-size display'
            ),
        ),
        migrations.AlterField(
            model_name='image',
            name='license',
            field=models.CharField(
                choices=[
                    ('ALL_RIGHTS_RESERVED', 'None (All rights reserved)'),
                    ('ATTRIBUTION_NON_COMMERCIAL_SHARE_ALIKE', 'Attribution-NonCommercial-ShareAlike Creative Commons'),
                    ('ATTRIBUTION_NON_COMMERCIAL', 'Attribution-NonCommercial Creative Commons'),
                    ('ATTRIBUTION_NON_COMMERCIAL_NO_DERIVS', 'Attribution-NonCommercial-NoDerivs Creative Commons'),
                    ('ATTRIBUTION', 'Attribution Creative Commons'),
                    ('ATTRIBUTION_SHARE_ALIKE', 'Attribution-ShareAlike Creative Commons'),
                    ('ATTRIBUTION_NO_DERIVS', 'Attribution-NoDerivs Creative Commons')
                ],
                default='ALL_RIGHTS_RESERVED',
                max_length=40,
                verbose_name='License'
            ),
        ),
        migrations.AlterField(
            model_name='image',
            name='mouse_hover_image',
            field=models.CharField(blank=True, default='SOLUTION', max_length=16, null=True),
        ),
        migrations.AlterField(
            model_name='image',
            name='watermark_size',
            field=models.CharField(
                choices=[('S', 'Small'), ('M', 'Medium'), ('L', 'Large')],
                default='M',
                help_text='The final font size will depend on how long your watermark is.',
                max_length=1,
                verbose_name='Size'
            ),
        ),
        migrations.AlterField(
            model_name='image',
            name='watermark_text',
            field=models.CharField(blank=True, max_length=128, null=True, verbose_name='Text'),
        ),
    ]

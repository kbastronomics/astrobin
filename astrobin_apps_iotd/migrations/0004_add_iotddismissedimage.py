# -*- coding: utf-8 -*-
# Generated by Django 1.11.29 on 2021-01-16 22:07
from __future__ import unicode_literals

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('astrobin_apps_iotd', '0003_add_iotdhiddenimage'),
    ]

    operations = [
        migrations.CreateModel(
            name='IotdDismissedImage',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('image', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='astrobin.Image')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='iotddismissedimage',
            unique_together=set([('user', 'image')]),
        ),
    ]

# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-08-23 13:41
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('basic', '0006_entrypoint_order'),
    ]

    operations = [
        migrations.AddField(
            model_name='person',
            name='last_lis',
            field=models.CharField(blank=True, max_length=100, verbose_name='Last known: lis_result_sourcedid'),
        ),
    ]
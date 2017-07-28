# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-07-28 10:18
from __future__ import unicode_literals

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('interactive', '0003_trigger_active'),
    ]

    operations = [
        migrations.RenameField(
            model_name='trigger',
            old_name='active',
            new_name='is_active',
        ),
        migrations.AddField(
            model_name='trigger',
            name='end_dt',
            field=models.DateTimeField(default=django.utils.timezone.now, verbose_name='Latest time for this trigger'),
        ),
        migrations.AddField(
            model_name='trigger',
            name='start_dt',
            field=models.DateTimeField(default=django.utils.timezone.now, verbose_name='Earliest time for this trigger'),
        ),
    ]

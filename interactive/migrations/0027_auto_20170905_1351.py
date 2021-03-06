# -*- coding: utf-8 -*-
# Generated by Django 1.11.1 on 2017-09-05 11:51
from __future__ import unicode_literals

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('interactive', '0026_reviewreport_entry_point'),
    ]

    operations = [
        migrations.AddField(
            model_name='trigger',
            name='deadline_dt',
            field=models.DateTimeField(blank=True, default=None, help_text='Sometimes you want a deadline to use in your logic. Set it here', null=True),
        ),
        migrations.AlterField(
            model_name='trigger',
            name='end_dt',
            field=models.DateTimeField(default=django.utils.timezone.now, help_text='Trigger will not run after the start date/time', verbose_name='Latest time for this trigger'),
        ),
        migrations.AlterField(
            model_name='trigger',
            name='start_dt',
            field=models.DateTimeField(default=django.utils.timezone.now, help_text='Trigger will not run prior to the start date/time', verbose_name='Earliest time for this trigger'),
        ),
    ]

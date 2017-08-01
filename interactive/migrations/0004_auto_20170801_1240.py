# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-08-01 10:40
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('interactive', '0003_auto_20170801_1237'),
    ]

    operations = [
        migrations.AlterField(
            model_name='reviewreport',
            name='trigger',
            field=models.ForeignKey(blank=True, help_text='Avoid using and see if this field is actually necessary', null=True, on_delete=django.db.models.deletion.CASCADE, to='interactive.Trigger'),
        ),
    ]

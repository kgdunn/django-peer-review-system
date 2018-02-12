# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2018-02-12 13:51
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('interactive', '0035_achieveconfig_deadline_dt'),
    ]

    operations = [
        migrations.AlterField(
            model_name='trigger',
            name='kwargs',
            field=models.TextField(blank=True, help_text='JSON settings. E.g. {"num_peers": 2}'),
        ),
    ]

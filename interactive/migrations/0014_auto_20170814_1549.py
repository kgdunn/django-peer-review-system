# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-08-14 13:49
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('interactive', '0013_auto_20170814_1546'),
    ]

    operations = [
        migrations.RenameField(
            model_name='achieveconfig',
            old_name='members',
            new_name='achievements',
        ),
    ]

# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-08-28 08:40
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('interactive', '0021_auto_20170825_1704'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='trigger',
            name='lower',
        ),
        migrations.RemoveField(
            model_name='trigger',
            name='upper',
        ),
    ]
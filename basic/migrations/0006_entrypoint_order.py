# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-08-23 11:29
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('basic', '0005_auto_20170728_1515'),
    ]

    operations = [
        migrations.AddField(
            model_name='entrypoint',
            name='order',
            field=models.PositiveSmallIntegerField(default=0, help_text='Used to order the achievement display in a course with many entry points.'),
        ),
    ]

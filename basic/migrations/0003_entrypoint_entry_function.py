# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-07-27 16:14
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('basic', '0002_auto_20170727_1741'),
    ]

    operations = [
        migrations.AddField(
            model_name='entrypoint',
            name='entry_function',
            field=models.CharField(default='', help_text='Django function, with syntax: "app_name.function_name"', max_length=100),
        ),
    ]

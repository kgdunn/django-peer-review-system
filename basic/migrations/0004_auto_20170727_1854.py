# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-07-27 16:54
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('basic', '0003_entrypoint_entry_function'),
    ]

    operations = [
        migrations.AlterField(
            model_name='entrypoint',
            name='entry_function',
            field=models.CharField(default='', help_text='Django function, with syntax: "app_name.views.function_name"', max_length=100),
        ),
    ]

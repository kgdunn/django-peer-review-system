# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-09-18 11:32
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('basic', '0015_auto_20170914_0943'),
    ]

    operations = [
        migrations.AlterField(
            model_name='entrypoint',
            name='full_URL',
            field=models.CharField(blank=True, default='', help_text='Full URL to the entry point in the given platform, startingwith "/"; eg: /course/12345/98765432', max_length=255),
        ),
    ]

# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-11-14 14:13
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('basic', '0022_person_hash_code'),
    ]

    operations = [
        migrations.AlterField(
            model_name='person',
            name='hash_code',
            field=models.CharField(blank=True, default='', max_length=16),
        ),
    ]

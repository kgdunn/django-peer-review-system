# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-10-17 11:45
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('interactive', '0033_achievement_note'),
    ]

    operations = [
        migrations.AlterField(
            model_name='achievement',
            name='note',
            field=models.TextField(blank=True, default='', help_text='Optional additional information', null=True),
        ),
    ]

# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-11-03 12:07
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('keyterm', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='keytermtask',
            name='definition_text',
            field=models.CharField(blank=True, help_text='Capped at 500 characters.', max_length=520, null=True),
        ),
    ]

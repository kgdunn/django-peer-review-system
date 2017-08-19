# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-08-19 10:56
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rubric', '0013_auto_20170818_1729'),
    ]

    operations = [
        migrations.AlterField(
            model_name='rubrictemplate',
            name='hook_function',
            field=models.CharField(blank=True, help_text='Hook that is called (with r_actual as only input)when the review is completed. Called with async() so it is OK if it is overhead intensive. Hook func must exist in the "interactive" views.py application.', max_length=100, null=True),
        ),
    ]

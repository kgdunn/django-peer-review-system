# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-08-25 13:17
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rubric', '0016_ritemtemplate_num_rows'),
    ]

    operations = [
        migrations.AlterField(
            model_name='rubrictemplate',
            name='hook_function',
            field=models.CharField(blank=True, default='', help_text='Hook that is called (with r_actual as only input)when the review is completed. Called with async() so it is OK if it is overhead intensive. Hook func must exist in the "interactive" views.py application.', max_length=100),
        ),
    ]
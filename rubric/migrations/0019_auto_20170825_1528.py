# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-08-25 13:28
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rubric', '0018_rubrictemplate_submit_button_text'),
    ]

    operations = [
        migrations.AlterField(
            model_name='rubrictemplate',
            name='submit_button_text',
            field=models.CharField(default='Submit your review', help_text='The text used on the submit button', max_length=255),
        ),
    ]

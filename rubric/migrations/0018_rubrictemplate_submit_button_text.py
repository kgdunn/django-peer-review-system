# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-08-25 13:27
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rubric', '0017_auto_20170825_1517'),
    ]

    operations = [
        migrations.AddField(
            model_name='rubrictemplate',
            name='submit_button_text',
            field=models.TextField(default='Submit your review', help_text='The text used on the submit button'),
        ),
    ]

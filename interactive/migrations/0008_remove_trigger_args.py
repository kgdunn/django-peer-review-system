# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-08-02 10:07
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('interactive', '0007_auto_20170802_1034'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='trigger',
            name='args',
        ),
    ]

# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-08-01 10:42
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('interactive', '0004_auto_20170801_1240'),
    ]

    operations = [
        migrations.AddField(
            model_name='reviewreport',
            name='have_emailed',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='reviewreport',
            name='reviewer',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='basic.Person'),
        ),
    ]

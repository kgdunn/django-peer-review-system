# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-08-16 13:26
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('interactive', '0016_achievement_last'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='evaluationreport',
            name='order',
        ),
        migrations.AlterField(
            model_name='evaluationreport',
            name='r_actual',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='rubric.RubricActual'),
        ),
    ]

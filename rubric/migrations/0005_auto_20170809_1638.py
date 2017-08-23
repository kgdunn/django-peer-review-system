# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-08-09 14:38
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rubric', '0004_rubrictemplate_show_maximum_score_per_item'),
    ]

    operations = [
        migrations.AlterField(
            model_name='rubricactual',
            name='status',
            field=models.CharField(choices=[('A', 'Assigned to grader'), ('P', 'Progressing...'), ('C', 'Completed'), ('L', 'Locked')], default='A', max_length=2),
        ),
    ]
# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2018-03-27 14:10
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rubric', '0020_rubrictemplate_minimum_word_count'),
    ]

    operations = [
        migrations.AlterField(
            model_name='rubricactual',
            name='status',
            field=models.CharField(choices=[('A', 'Assigned to grader'), ('V', 'Grader has viewed it, at least once'), ('P', 'Progressing...'), ('C', 'Completed'), ('L', 'Locked'), ('F', 'Forced')], default='A', max_length=2),
        ),
    ]

# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-08-11 10:45
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rubric', '0005_auto_20170809_1638'),
    ]

    operations = [
        migrations.AlterField(
            model_name='rubricactual',
            name='status',
            field=models.CharField(choices=[('A', 'Assigned to grader'), ('V', 'Grader has viewed it, at least once'), ('P', 'Progressing...'), ('C', 'Completed'), ('L', 'Locked')], default='A', max_length=2),
        ),
    ]

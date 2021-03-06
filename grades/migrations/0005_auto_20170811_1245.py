# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-08-11 10:45
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('basic', '0005_auto_20170728_1515'),
        ('grades', '0004_auto_20170728_1206'),
    ]

    operations = [
        migrations.CreateModel(
            name='LearnerChecklistItem',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('done', models.BooleanField()),
            ],
        ),
        migrations.CreateModel(
            name='LearnerChecklistTemplate',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('item_name', models.CharField(max_length=50)),
                ('order', models.PositiveSmallIntegerField(default=0)),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='grades.GradeCategory')),
            ],
        ),
        migrations.AddField(
            model_name='learnerchecklistitem',
            name='checklist',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='grades.LearnerChecklistTemplate'),
        ),
        migrations.AddField(
            model_name='learnerchecklistitem',
            name='learner',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='basic.Person'),
        ),
    ]

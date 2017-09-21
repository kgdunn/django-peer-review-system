# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-09-21 11:30
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('basic', '0018_auto_20170919_1203'),
    ]

    operations = [
        migrations.CreateModel(
            name='Email_Task',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('message', models.TextField(blank=True, default='')),
                ('subject', models.CharField(max_length=500)),
                ('sent_datetime', models.DateTimeField(auto_now=True)),
                ('entry_point', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='basic.EntryPoint')),
                ('learner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='basic.Person')),
            ],
        ),
    ]
# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-07-31 11:40
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('basic', '0005_auto_20170728_1515'),
        ('interactive', '0006_trigger_template'),
    ]

    operations = [
        migrations.CreateModel(
            name='GroupConfig',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('group_name', models.CharField(blank=True, help_text='If empty, will be auto-generated', max_length=100, null=True)),
                ('created_on', models.DateTimeField(auto_now_add=True)),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='basic.Course')),
            ],
        ),
        migrations.CreateModel(
            name='Membership',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('Submit', 'Submitter'), ('Review', 'Reviewer')], max_length=6)),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='interactive.GroupConfig')),
                ('learner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='basic.Person')),
            ],
        ),
        migrations.AddField(
            model_name='groupconfig',
            name='learner',
            field=models.ManyToManyField(through='interactive.Membership', to='basic.Person'),
        ),
        migrations.AlterUniqueTogether(
            name='groupconfig',
            unique_together=set([('group_name', 'course')]),
        ),
    ]

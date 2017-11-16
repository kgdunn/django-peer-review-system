# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-11-03 10:45
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
import keyterm.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('basic', '0021_person_last_grade_push_url'),
        ('submissions', '0003_auto_20170821_1735'),
    ]

    operations = [
        migrations.CreateModel(
            name='KeyTermSetting',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('keyterm', models.CharField(max_length=200)),
                ('max_thumbs', models.PositiveSmallIntegerField(default=3, help_text='Maximum number of thumbs up that can be awarded')),
                ('min_submissions_before_voting', models.PositiveSmallIntegerField(default=10, help_text='Minimum number of submissions before voting can start.')),
                ('deadline_for_voting', models.DateTimeField(default=keyterm.models.get_deadline)),
                ('terms_per_page', models.PositiveIntegerField(default=100, help_text='Number of terms shown per page.')),
                ('entry_point', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='basic.EntryPoint')),
            ],
            options={
                'verbose_name_plural': 'Key Term Settings',
                'verbose_name': 'Key Term Setting',
            },
        ),
        migrations.CreateModel(
            name='KeyTermTask',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image_modified', models.ImageField(blank=True, null=True, upload_to='')),
                ('image_thumbnail', models.ImageField(blank=True, null=True, upload_to='')),
                ('last_edited', models.DateTimeField(auto_now=True)),
                ('definition_text', models.CharField(blank=True, help_text='Capped at 500 characters.', max_length=505, null=True)),
                ('explainer_text', models.TextField(blank=True, null=True)),
                ('reference_text', models.CharField(blank=True, max_length=250, null=True)),
                ('is_in_draft', models.BooleanField(default=False, help_text='User is in draft mode')),
                ('is_in_preview', models.BooleanField(default=False, help_text='Preview mode')),
                ('is_finalized', models.BooleanField(default=False, help_text='User has submitted, and it is after the deadline')),
                ('is_submitted', models.BooleanField(default=False, help_text='User has submitted')),
                ('allow_to_share', models.BooleanField(default=True, help_text='Student is OK to share their work with class.')),
                ('image_raw', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='submissions.Submission')),
                ('keyterm', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='keyterm.KeyTermSetting')),
                ('learner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='basic.Person')),
            ],
            options={
                'verbose_name_plural': 'Key Term Tasks',
                'verbose_name': 'Key Term Task',
            },
        ),
        migrations.CreateModel(
            name='Thumbs',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('awarded', models.BooleanField(default=False)),
                ('last_edited', models.DateTimeField(auto_now_add=True)),
                ('keytermtask', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='keyterm.KeyTermTask')),
                ('voter', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='basic.Person')),
            ],
            options={
                'verbose_name_plural': 'Thumbs up',
                'verbose_name': 'Thumbs up',
            },
        ),
    ]
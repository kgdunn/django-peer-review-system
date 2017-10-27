# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-10-25 15:05
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
import keyterms.models


class Migration(migrations.Migration):

    dependencies = [
        ('basic', '0020_auto_20171024_1407'),
        ('keyterms', '0002_keytermtask_thumbs'),
    ]

    operations = [
        migrations.CreateModel(
            name='KeyTerm',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('keyterm', models.CharField(max_length=200)),
                ('max_thumbs', models.PositiveSmallIntegerField(default=3, help_text='Maximum number of thumbs up that can be awarded')),
                ('min_submissions_before_voting', models.PositiveSmallIntegerField(default=10, help_text='Minimum number of submissions before voting can start.')),
                ('deadline_for_voting', models.DateTimeField(default=keyterms.models.get_deadline)),
                ('terms_per_page', models.PositiveIntegerField(default=100, help_text='Number of terms shown per page.')),
                ('entry_point', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='basic.EntryPoint')),
            ],
            options={
                'verbose_name': 'Key Term Setting',
                'verbose_name_plural': 'Key Term Settings',
            },
        ),
        migrations.RemoveField(
            model_name='keytermtask',
            name='entry_point',
        ),
        migrations.RemoveField(
            model_name='keytermtask',
            name='settings',
        ),
        migrations.AlterField(
            model_name='keytermtask',
            name='keyterm',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='keyterms.KeyTerm'),
        ),
        migrations.DeleteModel(
            name='KeyTermSettings',
        ),
    ]
# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-09-13 11:55
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('basic', '0013_token_next_uri'),
    ]

    operations = [
        migrations.CreateModel(
            name='Group_Formation_Process',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='basic.Course')),
            ],
            options={
                'verbose_name': 'Group formation process',
                'verbose_name_plural': 'Group formation processes',
            },
        ),
        migrations.RemoveField(
            model_name='group',
            name='course',
        ),
        migrations.AddField(
            model_name='entrypoint',
            name='only_review_within_group',
            field=models.BooleanField(default=False, help_text='Checked: then students only review within; Unchecked: then students review outside their group.'),
        ),
        migrations.AlterField(
            model_name='entrypoint',
            name='uses_groups',
            field=models.BooleanField(default=False, help_text='Are groups used to restrict reviews?'),
        ),
        migrations.AddField(
            model_name='entrypoint',
            name='gf_process',
            field=models.ForeignKey(blank=True, default=None, help_text='Must be specified if groups are being used.', null=True, on_delete=django.db.models.deletion.CASCADE, to='basic.Group_Formation_Process'),
        ),
        migrations.AddField(
            model_name='group',
            name='gfp',
            field=models.ForeignKey(blank=True, default=None, on_delete=django.db.models.deletion.CASCADE, to='basic.Group_Formation_Process'),
        ),
    ]
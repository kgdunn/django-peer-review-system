# -*- coding: utf-8 -*-
# Generated by Django 1.11.1 on 2017-09-14 07:43
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('basic', '0014_auto_20170913_1355'),
    ]

    operations = [
        migrations.AlterField(
            model_name='entrypoint',
            name='only_review_within_group',
            field=models.BooleanField(default=False, help_text='If checked: then students only review within; If unchecked: then students review outside their group.'),
        ),
        migrations.AlterField(
            model_name='group',
            name='gfp',
            field=models.ForeignKey(blank=True, default=None, on_delete=django.db.models.deletion.CASCADE, to='basic.Group_Formation_Process', verbose_name='Group formation process'),
        ),
    ]
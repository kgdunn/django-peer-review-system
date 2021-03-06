# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-08-18 12:56
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('interactive', '0017_auto_20170816_1526'),
    ]

    operations = [
        migrations.AlterField(
            model_name='evaluationreport',
            name='evaluator',
            field=models.ForeignKey(help_text='The original submitter is the evaluator', on_delete=django.db.models.deletion.CASCADE, related_name='evaluator', to='basic.Person'),
        ),
        migrations.AlterField(
            model_name='evaluationreport',
            name='peer_reviewer',
            field=models.ForeignKey(help_text='The reviewer whose review is appended here', on_delete=django.db.models.deletion.CASCADE, related_name='peer_reviewer', to='basic.Person'),
        ),
        migrations.AlterField(
            model_name='evaluationreport',
            name='r_actual',
            field=models.ForeignKey(blank=True, help_text='Might be created just in time', null=True, on_delete=django.db.models.deletion.CASCADE, to='rubric.RubricActual'),
        ),
        migrations.AlterField(
            model_name='evaluationreport',
            name='submission',
            field=models.ForeignKey(blank=True, help_text='Might not known, until the reviewer visits the page', null=True, on_delete=django.db.models.deletion.CASCADE, to='submissions.Submission'),
        ),
    ]

# Generated by Django 3.1.4 on 2021-03-07 13:09

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('webgui', '0066_auto_20210307_1403'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='mod_name',
            field=models.CharField(blank=True, default='', help_text='Name of the mod to install. If no value is given, the scheme apx_{randomstring} will be used. Max length is 50 chars.', max_length=50, validators=[django.core.validators.RegexValidator('^[0-9a-zA-Z_]*$', 'Only alphanumeric characters and dashes are allowed.')]),
        ),
        migrations.AlterField(
            model_name='server',
            name='public_secret',
            field=models.CharField(blank=True, default='dgeaaccddhbdfhccehdd', help_text='The secret for the communication with the APX race control', max_length=500),
        ),
    ]
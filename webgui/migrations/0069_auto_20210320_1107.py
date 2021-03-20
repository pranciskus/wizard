# Generated by Django 3.1.4 on 2021-03-20 10:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('webgui', '0068_auto_20210307_1415'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='signup_active',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='server',
            name='public_secret',
            field=models.CharField(blank=True, default='geiaddhbebgabffehcbg', help_text='The secret for the communication with the APX race control', max_length=500),
        ),
    ]

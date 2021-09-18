# Generated by Django 3.1.4 on 2021-09-12 10:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('webgui', '0180_auto_20210912_1203'),
    ]

    operations = [
        migrations.AlterField(
            model_name='server',
            name='public_secret',
            field=models.CharField(blank=True, default='icfaddcbdagiebaiccbh', help_text='The secret for the communication with the APX race control', max_length=500),
        ),
    ]
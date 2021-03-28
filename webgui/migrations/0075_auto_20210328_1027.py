# Generated by Django 3.1.4 on 2021-03-28 08:27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('webgui', '0074_auto_20210328_0914'),
    ]

    operations = [
        migrations.AlterField(
            model_name='racesessions',
            name='description',
            field=models.CharField(default='Add description', max_length=200),
        ),
        migrations.AlterField(
            model_name='server',
            name='public_secret',
            field=models.CharField(blank=True, default='facfhgbaideiaedbgafd', help_text='The secret for the communication with the APX race control', max_length=500),
        ),
    ]

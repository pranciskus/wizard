# Generated by Django 3.1.4 on 2021-01-09 18:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('webgui', '0022_auto_20210109_1638'),
    ]

    operations = [
        migrations.AddField(
            model_name='server',
            name='status',
            field=models.TextField(blank=True, default=None, null=True),
        ),
    ]

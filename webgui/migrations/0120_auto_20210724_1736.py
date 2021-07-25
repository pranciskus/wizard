# Generated by Django 3.1.4 on 2021-07-24 15:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('webgui', '0119_auto_20210724_1140'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='server',
            name='status_failures',
        ),
        migrations.AlterField(
            model_name='server',
            name='public_secret',
            field=models.CharField(blank=True, default='dehbdifadgchbhehdfae', help_text='The secret for the communication with the APX race control', max_length=500),
        ),
    ]
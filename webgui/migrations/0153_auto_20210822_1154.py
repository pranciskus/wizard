# Generated by Django 3.1.4 on 2021-08-22 09:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('webgui', '0152_auto_20210822_1054'),
    ]

    operations = [
        migrations.AddField(
            model_name='servercron',
            name='message',
            field=models.TextField(blank=True, default=None, help_text='Message to send', null=True),
        ),
        migrations.AlterField(
            model_name='server',
            name='public_secret',
            field=models.CharField(blank=True, default='cbcaggegfidfefaccbgh', help_text='The secret for the communication with the APX race control', max_length=500),
        ),
    ]
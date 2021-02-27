# Generated by Django 3.1.4 on 2021-02-27 19:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('webgui', '0061_component_mask_positions'),
    ]

    operations = [
        migrations.RenameField(
            model_name='component',
            old_name='livery_mask',
            new_name='numberplate_template',
        ),
        migrations.AlterField(
            model_name='entryfile',
            name='mask_added',
            field=models.BooleanField(default=False, help_text='Will be checked if a set of numberpaltes/ livery masks were added. Uncheck to force update.'),
        ),
    ]

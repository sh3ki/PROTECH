# Generated by Django 3.0.5 on 2024-12-06 16:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('school', '0006_auto_20241206_1615'),
    ]

    operations = [
        migrations.AlterField(
            model_name='student',
            name='section',
            field=models.IntegerField(),
        ),
    ]

# Generated by Django 3.0.5 on 2025-01-08 23:30

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('school', '0008_auto_20250107_0758'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='student',
            name='grade',
        ),
        migrations.AlterField(
            model_name='student',
            name='section',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='school.Section'),
        ),
    ]

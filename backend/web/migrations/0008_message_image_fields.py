# Generated migrations for image fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('web', '0007_alter_systemprompt_prompt'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='image_url',
            field=models.CharField(max_length=500, blank=True, null=True),
        ),
        migrations.AddField(
            model_name='message',
            name='image_caption',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='message',
            name='image_analysis',
            field=models.JSONField(blank=True, null=True),
        ),
    ]
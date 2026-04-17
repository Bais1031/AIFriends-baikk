# 修复image_caption字段的NOT NULL约束

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('web', '0008_message_image_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='message',
            name='image_caption',
            field=models.TextField(blank=True, null=True),
        ),
    ]

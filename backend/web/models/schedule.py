from django.db import models
from django.utils.timezone import now

from web.models.user import UserProfile


REPEAT_CHOICES = [
    ('none', '不重复'),
    ('daily', '每天'),
    ('weekly', '每周'),
    ('monthly', '每月'),
]

STATUS_CHOICES = [
    ('pending', '待完成'),
    ('completed', '已完成'),
    ('cancelled', '已取消'),
]

SOURCE_CHOICES = [
    ('text', '文字'),
    ('voice', '语音'),
    ('image', '图片'),
    ('agent', 'Agent'),
]


class Schedule(models.Model):
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField(default='', blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=200, default='', blank=True)
    repeat_type = models.CharField(max_length=20, choices=REPEAT_CHOICES, default='none')
    reminder_before = models.IntegerField(default=30)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='text')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    create_time = models.DateTimeField(default=now)
    update_time = models.DateTimeField(default=now)

    class Meta:
        ordering = ['start_time']

    def __str__(self):
        return self.title

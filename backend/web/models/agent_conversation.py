from django.db import models
from django.utils.timezone import now

from web.models.user import UserProfile


class AgentConversation(models.Model):
    """日程 Agent 对话历史"""
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    role = models.CharField(max_length=20)  # 'human' or 'ai'
    content = models.TextField()
    create_time = models.DateTimeField(default=now)

    class Meta:
        ordering = ['create_time']

    def __str__(self):
        return f"{self.user.user.username} - {self.role}: {self.content[:50]}"

from django.db import models
from django.utils.timezone import now, localtime
from pgvector.django import VectorField, HnswIndex

from web.models.character import Character
from web.models.user import UserProfile


class Friend(models.Model):
    me = models.ForeignKey(UserProfile,on_delete=models.CASCADE)
    character = models.ForeignKey(Character,on_delete=models.CASCADE)
    memory = models.TextField(default="", max_length=5000, blank=True, null=True)
    conversation_summary = models.TextField(default="", blank=True)
    summary_message_count = models.IntegerField(default=0)
    create_time = models.DateTimeField(default=now)
    update_time = models.DateTimeField(default=now)

    def __str__(self):
        return f"{self.character.name} - {self.me.user.username} - {localtime(self.create_time).strftime('%Y-%m-%d %H:%M:%S')}"


class MemoryItem(models.Model):
    """结构化长期记忆条目"""
    CATEGORY_CHOICES = [
        ('preference', '偏好'),
        ('event', '事件'),
        ('fact', '事实'),
        ('emotion', '情感'),
        ('general', '通用'),
    ]

    friend = models.ForeignKey(Friend, on_delete=models.CASCADE, related_name='memories')
    content = models.TextField()
    category = models.CharField(max_length=32, default='general', choices=CATEGORY_CHOICES)
    importance = models.FloatField(default=0.5)
    weight = models.FloatField(default=0.5)
    access_count = models.IntegerField(default=0)
    embedding = VectorField(dimensions=1024, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_accessed = models.DateTimeField(default=now)

    class Meta:
        ordering = ['-weight']
        indexes = [
            HnswIndex(
                name='web_memoryitem_embedding_hnsw',
                fields=['embedding'],
                opclasses=['vector_cosine_ops'],
                m=16,
                ef_construction=64,
            ),
        ]

    def __str__(self):
        return f"[{self.category}] {self.content[:50]} (w={self.weight:.2f})"


class Message(models.Model):
    friend = models.ForeignKey(Friend,on_delete=models.CASCADE)
    user_message = models.TextField(max_length=500)
    input = models.TextField(max_length=10000)
    output = models.TextField(max_length=500)
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)
    image_url = models.CharField(max_length=500, blank=True, null=True)
    image_caption = models.TextField(blank=True, null=True)
    image_analysis = models.JSONField(blank=True, null=True)
    create_time = models.DateTimeField(default=now)

    def __str__(self):
        return f"{self.friend.character.name} - {self.friend.me.user.username} - {self.user_message[:50]} - {localtime(self.create_time).strftime('%Y-%m-%d %H:%M:%S')}"


class SystemPrompt(models.Model):
    title = models.CharField(max_length=100)
    order_number = models.IntegerField(default=0)
    prompt = models.TextField(max_length=10000)
    create_time = models.DateTimeField(default=now)
    update_time = models.DateTimeField(default=now)

    def __str__(self):
        return f"{self.title} - {self.order_number} - {self.prompt[:50]} - {localtime(self.create_time).strftime('%Y-%m-%d %H:%M:%S')}"

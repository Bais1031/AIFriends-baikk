from django.contrib import admin
from web.models.user import UserProfile
from web.models.character import Character
from web.models.friend import Friend, MemoryItem, Message, SystemPrompt


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    raw_id_fields = ("user",) #逗号不要删，这里传一个列表，括号表示一个元素 加逗号变为列表


@admin.register(Character)
class CharacterAdmin(admin.ModelAdmin):
    raw_id_fields = ("author",)


@admin.register(Friend)
class FriendAdmin(admin.ModelAdmin):
    raw_id_fields = ('me', 'character',)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    raw_id_fields = ("friend",)


admin.site.register(SystemPrompt)


@admin.register(MemoryItem)
class MemoryItemAdmin(admin.ModelAdmin):
    list_display = ('content', 'category', 'importance', 'weight', 'access_count', 'created_at')
    list_filter = ('category',)
    search_fields = ('content',)
    exclude = ('embedding',)
    raw_id_fields = ('friend',)
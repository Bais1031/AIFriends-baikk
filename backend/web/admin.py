from django.contrib import admin
from web.models.user import UserProfile
from web.models.character import Character
from web.models.friend import Friend


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    raw_id_fields = ("user",) #逗号不要删，这里传一个列表，括号表示一个元素 加逗号变为列表


@admin.register(Character)
class CharacterAdmin(admin.ModelAdmin):
    raw_id_fields = ("author",)


@admin.register(Friend)
class FriendAdmin(admin.ModelAdmin):
    raw_id_fields = ('me', 'character',)

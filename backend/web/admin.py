from django.contrib import admin
from web.models.user import UserProfile

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    raw_id_fields = ("user",) #逗号不要删，这里传一个列表，括号表示一个元素 加逗号变为列表

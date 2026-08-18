from django.contrib import admin
from .models import ChatThread, ChatMessage


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ['sender', 'body', 'created_at', 'read_at']


@admin.register(ChatThread)
class ChatThreadAdmin(admin.ModelAdmin):
    list_display = ['student', 'is_closed', 'created_at', 'updated_at']
    list_filter = ['is_closed']
    search_fields = ['student__matric_number']
    raw_id_fields = ['student']
    inlines = [ChatMessageInline]

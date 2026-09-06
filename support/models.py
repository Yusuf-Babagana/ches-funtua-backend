from django.db import models


class ChatThread(models.Model):
    """
    One persistent support conversation per student. Deliberately kept
    separate from academics.StudentQuery (a single-record ticket) --
    this is a real multi-message thread, polled by the client rather
    than pushed (no websocket support assumed on the deployment target).
    """
    student = models.ForeignKey('users.Student', on_delete=models.CASCADE, related_name='chat_threads')
    is_closed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Chat Thread'
        verbose_name_plural = 'Chat Threads'

    def __str__(self):
        return f"Support chat - {self.student.matric_number}"


class ChatMessage(models.Model):
    thread = models.ForeignKey(ChatThread, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, related_name='chat_messages_sent')
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Chat Message'
        verbose_name_plural = 'Chat Messages'

    def __str__(self):
        return f"{self.sender}: {self.body[:40]}"

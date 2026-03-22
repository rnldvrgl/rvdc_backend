from django.db import models


class FacebookPage(models.Model):
    """Stores Facebook Page configuration for messaging integration."""

    page_id = models.CharField(max_length=100, unique=True)
    page_name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.page_name

    class Meta:
        ordering = ["-created_at"]


class Conversation(models.Model):
    """A conversation thread with a Facebook user."""

    page = models.ForeignKey(
        FacebookPage,
        on_delete=models.CASCADE,
        related_name="conversations",
    )
    fb_user_id = models.CharField(max_length=100)
    fb_user_name = models.CharField(max_length=255, blank=True, default="")
    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fb_conversations",
    )
    last_message_at = models.DateTimeField(null=True, blank=True)
    last_message_preview = models.CharField(max_length=255, blank=True, default="")
    unread_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_message_at"]
        unique_together = ["page", "fb_user_id"]
        indexes = [
            models.Index(fields=["-last_message_at"]),
            models.Index(fields=["fb_user_id"]),
        ]

    def __str__(self):
        return f"{self.fb_user_name or self.fb_user_id}"


class Message(models.Model):
    """An individual message within a conversation."""

    DIRECTION_CHOICES = [
        ("in", "Incoming"),
        ("out", "Outgoing"),
    ]

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    direction = models.CharField(max_length=3, choices=DIRECTION_CHOICES)
    text = models.TextField(blank=True, default="")
    fb_message_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    attachments = models.JSONField(default=list, blank=True)
    sent_by = models.ForeignKey(
        "users.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Staff user who sent outgoing message",
    )
    timestamp = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timestamp"]
        indexes = [
            models.Index(fields=["conversation", "timestamp"]),
            models.Index(fields=["fb_message_id"]),
        ]

    def __str__(self):
        return f"[{self.direction}] {self.text[:50]}"

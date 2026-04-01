from django.db import models


class ActiveClientManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class Client(models.Model):
    full_name = models.CharField(max_length=100)
    contact_number = models.CharField(max_length=15, null=True, blank=True, unique=True)
    province = models.CharField(max_length=50, blank=True, default="")
    city = models.CharField(max_length=50, blank=True, default="")
    barangay = models.CharField(max_length=50, null=True, blank=True)
    address = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    is_blocklisted = models.BooleanField(default=False)

    objects = ActiveClientManager()
    all_objects = models.Manager()

    def __str__(self):
        return f"{self.full_name} - {self.contact_number}"

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["full_name"]),
            models.Index(fields=["is_deleted"]),
            models.Index(fields=["is_deleted", "-created_at"]),
        ]

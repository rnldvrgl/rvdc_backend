from django.db import models


class ActiveClientManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class Client(models.Model):
    full_name = models.CharField(max_length=100)
    contact_number = models.CharField(max_length=15)
    province = models.CharField(max_length=50)
    city = models.CharField(max_length=50)
    barangay = models.CharField(max_length=50)
    address = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    objects = ActiveClientManager()
    all_objects = models.Manager()

    def __str__(self):
        return f"{self.full_name} - {self.contact_number}"

    class Meta:
        ordering = ["-created_at"]

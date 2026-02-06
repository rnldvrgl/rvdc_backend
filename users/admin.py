from django.contrib import admin
from users.models import CustomUser, SystemSettings


@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    list_display = ['id', 'birthday_greeting_enabled', 'updated_at']
    fieldsets = [
        ('Birthday Greeting Settings', {
            'fields': [
                'birthday_greeting_enabled',
                'birthday_greeting_title',
                'birthday_greeting_message',
            ]
        }),
        ('Metadata', {
            'fields': ['updated_at'],
            'classes': ['collapse'],
        }),
    ]
    readonly_fields = ['updated_at']
    
    def has_add_permission(self, request):
        # Only allow one instance (singleton)
        return not SystemSettings.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        # Don't allow deleting the settings
        return False


# Register your models here
admin.site.register(CustomUser)

from django.contrib import admin
from users.models import CustomUser, SystemSettings


@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    list_display = ['id', 'birthday_greeting_enabled', 'birthday_greeting_variant', 'updated_at']
    fieldsets = [
        ('Birthday Greeting Settings', {
            'fields': [
                'birthday_greeting_enabled',
                'birthday_greeting_variant',
                'birthday_greeting_title',
                'birthday_greeting_message',
                'birthday_greeting_button_text',
            ]
        }),
        ('Display Options', {
            'fields': [
                'birthday_greeting_show_confetti',
                'birthday_greeting_show_emojis',
            ]
        }),
        ('Emoji Decorations', {
            'fields': [
                'birthday_greeting_male_emojis',
                'birthday_greeting_female_emojis',
            ],
            'description': 'Customize emoji decorations based on employee gender. Use comma-separated emojis (e.g., 🎈,🎊,🎁,🎉,🍺)'
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

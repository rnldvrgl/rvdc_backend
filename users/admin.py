from django.contrib import admin
from users.models import CustomUser, SystemSettings, CashAdvance


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


@admin.register(CashAdvance)
class CashAdvanceAdmin(admin.ModelAdmin):
    list_display = ['employee', 'amount', 'date', 'created_by', 'created_at']
    list_filter = ['date', 'created_at']
    search_fields = ['employee__first_name', 'employee__last_name', 'reason']
    readonly_fields = ['created_at', 'updated_at', 'created_by']
    date_hierarchy = 'date'
    
    def save_model(self, request, obj, form, change):
        if not change:  # Only set created_by on creation
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


# Register your models here
admin.site.register(CustomUser)

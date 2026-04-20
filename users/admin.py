from django.contrib import admin
from users.models import CustomUser, SystemSettings, CashAdvanceMovement


@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'birthday_greeting_enabled',
        'birthday_greeting_variant',
        'maintenance_mode',
        'google_sheets_sync_enabled',
        'updated_at',
    ]
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
        ('Business Operations', {
            'fields': [
                'maintenance_mode',
                'check_stock_on_sale',
                'notification_sound',
            ]
        }),
        ('Google Sheets Sync', {
            'fields': [
                'google_sheets_sync_enabled',
                'google_sheets_spreadsheet_id',
                'google_sheets_worksheet_name',
                'google_sheets_sub_stall_type',
                'google_service_account_json',
            ],
            'description': 'Configure automatic sub-stall sales sync to Google Sheets using a service account JSON.',
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


@admin.register(CashAdvanceMovement)
class CashAdvanceMovementAdmin(admin.ModelAdmin):
    list_display = ['employee', 'movement_type', 'amount', 'balance_after', 'date', 'created_by', 'created_at']
    list_filter = ['movement_type', 'date', 'created_at']
    search_fields = ['employee__first_name', 'employee__last_name', 'description', 'reference']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'balance_after']
    date_hierarchy = 'date'

    def save_model(self, request, obj, form, change):
        if not change:  # Only set created_by on creation
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


# Register your models here
admin.site.register(CustomUser)

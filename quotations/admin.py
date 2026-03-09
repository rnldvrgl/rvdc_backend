from django.contrib import admin

from .models import Quotation, QuotationItem, QuotationTermsTemplate


class QuotationItemInline(admin.TabularInline):
    model = QuotationItem
    extra = 1


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ["id", "client_name", "quote_date", "total", "status", "created_at"]
    list_filter = ["status", "is_deleted"]
    search_fields = ["client_name", "project_description"]
    inlines = [QuotationItemInline]


@admin.register(QuotationTermsTemplate)
class QuotationTermsTemplateAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "category", "is_default", "is_active", "created_at"]
    list_filter = ["category", "is_default", "is_active"]
    search_fields = ["name"]

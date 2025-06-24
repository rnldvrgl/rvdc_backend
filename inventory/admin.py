from django.contrib import admin
from inventory.models import Item, Stall, Stock

# Register your models here.
admin.site.register(Item)
admin.site.register(Stall)
admin.site.register(Stock)

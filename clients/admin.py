from django.contrib import admin
from clients.models import Client, ClientFundDeposit

# Register your models here.
admin.site.register(Client)

admin.site.register(ClientFundDeposit)

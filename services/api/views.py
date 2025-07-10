# from rest_framework import viewsets, filters
# from rest_framework.exceptions import ValidationError
# from django_filters.rest_framework import DjangoFilterBackend
# from rest_framework.permissions import IsAuthenticated
# from services.models import ServiceRequest, ServiceStep
# from .serializers import ServiceRequestSerializer, ServiceStepSerializer
# from sales.models import SalesTransaction, SalesItem
# from django.utils import timezone
# from inventory.models import StockTransfer, Item, Stall
# from users.models import CustomUser
# from services.models import ServiceRequestItem


# class ServiceRequestViewSet(viewsets.ModelViewSet):
#     queryset = ServiceRequest.objects.all().order_by("-date_received")
#     serializer_class = ServiceRequestSerializer
#     permission_classes = [IsAuthenticated]
#     filter_backends = [DjangoFilterBackend, filters.SearchFilter]
#     filterset_fields = ["client__full_name", "client__phone"]
#     search_fields = ["client__full_name", "client__phone"]

#     def perform_update(self, serializer):
#         instance = serializer.instance
#         validated_data = serializer.validated_data
#         used_items_data = self.request.data.get("used_items", [])
#         technicians_data = validated_data.pop("technicians", None)

#         # Remove nested fields that shouldn't go to update()
#         validated_data.pop("used_items", None)

#         # Update regular fields
#         for attr, value in validated_data.items():
#             setattr(instance, attr, value)
#         instance.save()

#         # Update technicians if provided
#         if technicians_data is not None:
#             instance.technicians.set(technicians_data)

#         # Handle used_items update or add
#         for item_data in used_items_data:
#             try:
#                 item = Item.objects.get(pk=item_data["item"])
#                 stall = Stall.objects.get(pk=item_data["deducted_from_stall"])
#                 user = CustomUser.objects.get(pk=item_data["deducted_by"])

#                 obj, created = ServiceRequestItem.objects.update_or_create(
#                     service_request=instance,
#                     item=item,
#                     defaults={
#                         "quantity_used": item_data["quantity_used"],
#                         "deducted_from_stall": stall,
#                         "deducted_by": user,
#                     },
#                 )
#                 print(f"Used item {'created' if created else 'updated'}:", obj)
#             except Exception as e:
#                 print("Error updating/creating used item:", e)

#         # Handle sales transaction logic if paid
#         if (
#             instance.payment_status == "paid"
#             and instance.sales_transaction is None
#             and instance.total_payment
#             and instance.final_price
#         ):
#             clerk_stall = self.request.user.assigned_stall
#             if not clerk_stall:
#                 raise ValidationError(
#                     "Sales transaction could not be created because the clerk is not assigned to a stall."
#                 )

#             sales_tx = SalesTransaction.objects.create(
#                 sales_clerk=self.request.user,
#                 stall=clerk_stall,
#                 client=instance.client,
#                 total_payment=instance.total_payment,
#                 created_at=instance.payment_date or timezone.now(),
#             )

#             for used_item in instance.used_items.select_related(
#                 "item", "deducted_from_stall"
#             ):
#                 item = used_item.item
#                 quantity = used_item.quantity_used
#                 retail_price = item.retail_price
#                 final_price = quantity * retail_price

#                 if used_item.deducted_from_stall != clerk_stall:
#                     StockTransfer.objects.create(
#                         item=item,
#                         quantity=quantity,
#                         to_stall=clerk_stall,
#                         transferred_by=self.request.user,
#                     )

#                 SalesItem.objects.create(
#                     transaction=sales_tx,
#                     item=item,
#                     quantity=quantity,
#                     retail_price=retail_price,
#                     final_price=final_price,
#                 )

#             instance.sales_transaction = sales_tx
#             instance.save(update_fields=["sales_transaction"])


# class ServiceStepViewSet(viewsets.ModelViewSet):
#     queryset = ServiceStep.objects.all().order_by("-performed_on")
#     serializer_class = ServiceStepSerializer
#     permission_classes = [IsAuthenticated]
#     filter_backends = [DjangoFilterBackend, filters.SearchFilter]
#     filterset_fields = ["service_request__client__full_name", "service_type"]
#     search_fields = ["service_request__client__full_name", "service_type"]

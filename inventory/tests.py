from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from inventory.models import Stall, ProductCategory, Item, StockRoomStock

User = get_user_model()


class InventoryTests(APITestCase):
    def setUp(self):
        self.stall = Stall.objects.create(name="Main Stall", location="Downtown")
        self.admin_user = User.objects.create_user(
            username="admin",
            password="adminpass",
            role="admin",
            assigned_stall=self.stall,
            is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin_user)

        self.category = ProductCategory.objects.create(name="Electronics")
        self.item = Item.objects.create(
            name="Laptop",
            sku="LP-100",
            srp="1000.00",
            category=self.category,
            unit_of_measure="unit",
        )

    def test_create_product_category(self):
        print("\nRunning: test_create_product_category")
        url = reverse("category-list-create")
        data = {"name": "Stationery"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Stationery")

    def test_create_item(self):
        print("\nRunning: test_create_item")
        url = reverse("item-list-create")
        data = {
            "name": "Projector",
            "sku": "PJ-001",
            "unit_of_measure": "pcs",
            "srp": "500.00",
            "category": self.category.id,
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Projector")

    def test_create_stockroom_stock(self):
        print("\nRunning: test_create_stockroom_stock")
        url = reverse("stock-room-stock")
        data = {
            "item": self.item.id,
            "quantity": 25,
            "low_stock_threshold": 5,
            # "stall": self.stall.id,
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["quantity"], 25)
        self.assertEqual(response.data["item"], self.item.id)

    def test_get_item_list(self):
        print("\nRunning: test_get_item_list")
        url = reverse("item-list-create")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 1)

    def test_get_single_item(self):
        print("\nRunning: test_get_single_item")
        url = reverse("item-detail", kwargs={"pk": self.item.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], self.item.name)

    def test_update_item(self):
        print("\nRunning: test_update_item")
        url = reverse("item-detail", kwargs={"pk": self.item.pk})
        data = {
            "name": "Updated Laptop",
            "sku": "LP-101",
            "unit_of_measure": "roll",
            "srp": "1200.00",
            "category": self.category.id,
        }
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Updated Laptop")

    def test_soft_delete_item(self):
        print("\nRunning: test_soft_delete_item")
        url = reverse("item-detail", kwargs={"pk": self.item.pk})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Confirm it's not returned in default list
        list_response = self.client.get(reverse("item-list-create"))
        items = list_response.data.get("results", list_response.data)
        self.assertFalse(any(item["id"] == self.item.id for item in items))

    def test_create_duplicate_category(self):
        print("\nRunning: test_create_duplicate_category")
        url = reverse("category-list-create")
        data = {"name": "Electronics"}  # Already created in setUp
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_low_stock_warning(self):
        print("\nRunning: test_low_stock_warning")
        StockRoomStock.objects.create(
            item=self.item,
            quantity=3,
            low_stock_threshold=5,
        )
        url = reverse("stock-room-stock")  # Adjust if needed
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        stocks = response.data.get("results", response.data)
        item_stock = next((s for s in stocks if s["item"] == self.item.id), None)
        self.assertIsNotNone(item_stock)
        self.assertLess(item_stock["quantity"], item_stock["low_stock_threshold"])

    def test_unauthenticated_access_denied(self):
        print("\nRunning: test_unauthenticated_access_denied")
        self.client.force_authenticate(user=None)
        url = reverse("item-list-create")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

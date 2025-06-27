from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from users.models import CustomUser
from inventory.models import Stall
from expenses.models import Expense
from rest_framework_simplejwt.tokens import RefreshToken


class ExpenseAPITestCase(APITestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="testuser", password="testpass"
        )
        self.client.force_authenticate(user=self.user)

        self.stall = Stall.objects.create(name="Stall A")

        self.expense1 = Expense.objects.create(
            stall=self.stall,
            total_price=100.00,
            description="Cleaning supplies",
            created_by=self.user,
            source="manual",
        )

        self.expense2 = Expense.objects.create(
            stall=self.stall,
            total_price=200.00,
            description="New chairs",
            created_by=self.user,
            source="manual",
        )

        self.list_url = reverse("expense-list")

    def test_list_expenses_authenticated(self):
        print("Testing list expenses with authenticated user")
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertEqual(response.data["count"], 2)

    def test_list_expenses_unauthenticated(self):
        print("Testing list expenses with unauthenticated user")
        self.client.logout()
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_expense(self):
        print("Testing create expense with authenticated user")
        data = {
            "stall": self.stall.id,
            "total_price": "150.00",
            "description": "Misc items",
        }
        response = self.client.post(self.list_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["created_by"], self.user.id)
        self.assertEqual(response.data["source"], "manual")

    def test_retrieve_expense_detail(self):
        print("Testing retrieve expense detail")
        url = reverse("expense-detail", args=[self.expense1.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["description"], self.expense1.description)

    def test_update_expense_description(self):
        print("Testing update expense description")
        url = reverse("expense-detail", args=[self.expense1.id])
        response = self.client.patch(url, {"description": "Updated description"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.expense1.refresh_from_db()
        self.assertEqual(self.expense1.description, "Updated description")

    def test_delete_expense(self):
        print("Testing delete expense")
        url = reverse("expense-detail", args=[self.expense1.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Expense.objects.filter(id=self.expense1.id).exists())

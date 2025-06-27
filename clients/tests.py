from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from clients.models import Client
from django.urls import reverse

User = get_user_model()


class ClientAPITestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client.force_authenticate(user=self.user)

        self.client1 = Client.objects.create(
            full_name="Alice Smith",
            phone="1234567890",
            province="Province1",
            city="City1",
            barangay="Barangay1",
            address="Address1",
        )
        self.client2 = Client.objects.create(
            full_name="Bob Jones",
            phone="0987654321",
            province="Province2",
            city="City2",
            barangay="Barangay2",
            address="Address2",
        )

        self.list_url = reverse("client-list-create")
        self.detail_url = lambda pk: reverse("client-detail", args=[pk])

    def test_list_clients_authenticated(self):
        print("Testing list clients with authentication")
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 2)

    def test_filter_clients_by_full_name(self):
        print("Testing filter clients by full name")
        response = self.client.get(self.list_url, {"full_name": "Alice Smith"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["full_name"], "Alice Smith")

    def test_search_clients_by_phone(self):
        print("Testing search clients by phone")
        response = self.client.get(self.list_url, {"search": "0987"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["phone"], "0987654321")

    def test_create_client(self):
        print("Testing create client")
        data = {
            "full_name": "Charlie Brown",
            "phone": "5555555555",
            "province": "Province3",
            "city": "City3",
            "barangay": "Barangay3",
            "address": "Address3",
        }
        response = self.client.post(self.list_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Client.objects.filter(full_name="Charlie Brown").exists())

    def test_retrieve_client_detail(self):
        print("Testing retrieve client detail")
        response = self.client.get(self.detail_url(self.client1.pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["full_name"], self.client1.full_name)

    def test_update_client(self):
        print("Testing update client")
        data = {"full_name": "Updated Name"}
        response = self.client.patch(self.detail_url(self.client1.pk), data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client1.refresh_from_db()
        self.assertEqual(self.client1.full_name, "Updated Name")

    def test_soft_delete_client(self):
        print("Testing soft delete client")
        response = self.client.delete(self.detail_url(self.client1.pk))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.client1.refresh_from_db()
        self.assertTrue(self.client1.is_deleted or not self.client1.is_active)

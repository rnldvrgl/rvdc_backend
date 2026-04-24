"""
Test suite for aircon unit sales allocation split.

Tests the business logic that splits aircon unit sales between:
- Main stall: margin portion (selling_price - cost_price)
- Sub stall: cost portion (cost_price)

This ensures correct revenue attribution in the two-stall system.
"""

from decimal import Decimal

from clients.models import Client
from django.test import TransactionTestCase
from installations.models import AirconBrand, AirconModel, AirconUnit
from inventory.models import Item, ProductCategory, Stall, Stock
from rest_framework.exceptions import ValidationError
from users.models import CustomUser, SystemSettings
from utils.enums import ApplianceStatus, ServiceType

from services.business_logic import (
    RevenueCalculator,
    ServiceCompletionHandler,
    get_main_stall,
    get_sub_stall,
)
from services.models import ApplianceType, Service, ServiceAppliance


class AirconUnitAllocationTestSetup(TransactionTestCase):
    """Base setup for aircon unit allocation tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create system stalls
        cls.main_stall = Stall.objects.create(
            name="Main",
            location="Services",
            stall_type="main",
            is_system=True,
            inventory_enabled=False,
        )

        cls.sub_stall = Stall.objects.create(
            name="Sub",
            location="Parts",
            stall_type="sub",
            is_system=True,
            inventory_enabled=True,
        )

        # Create test user
        cls.user = CustomUser.objects.create_user(
            username="testuser", password="testpass123", role="admin"
        )

        # Create test client
        cls.client_obj = Client.objects.create(
            name="Test Client", email="test@example.com", phone="555-1234"
        )

        # Create appliance type
        cls.appliance_type = ApplianceType.objects.create(
            name="Air Conditioner", category="appliance"
        )

        # Create aircon brand and model
        cls.brand = AirconBrand.objects.create(name="Midea")
        cls.model = AirconModel.objects.create(
            brand=cls.brand,
            name="1.5 HP Standard",
            retail_price=Decimal("22000.00"),
            cost_price=Decimal("14500.00"),
            promo_price=None,  # No promo
        )

        # Create parts for testing
        category = ProductCategory.objects.create(
            name="AC Parts", description="Air conditioning parts"
        )
        cls.capacitor = Item.objects.create(
            name="Capacitor",
            sku="CAP-001",
            category=category,
            retail_price=Decimal("500.00"),
        )

        # Create stock in Sub stall
        cls.capacitor_stock = Stock.objects.create(
            item=cls.capacitor,
            stall=cls.sub_stall,
            quantity=100,
            reserved_quantity=0,
            low_stock_threshold=10,
        )

    def setUp(self):
        """Reset for each test."""
        super().setUp()


class TestAirconUnitRevenueAllocation(AirconUnitAllocationTestSetup):
    """Test that aircon unit prices are split correctly between stalls."""

    def test_installation_service_aircon_unit_revenue_split(self):
        """
        Test that aircon unit revenue is split correctly:
        - Selling price: ₱22,000
        - Cost price: ₱14,500
        - Main revenue: ₱7,500 (margin)
        - Sub revenue: ₱14,500 (cost)
        """
        # Create installation service
        service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            service_type=ServiceType.INSTALLATION,
        )

        # Create appliance for the service
        appliance = ServiceAppliance.objects.create(
            service=service,
            appliance_type=self.appliance_type,
            labor_fee=Decimal("1000.00"),
        )

        # Create and link aircon unit
        unit = AirconUnit.objects.create(
            model=self.model,
            serial_number="TEST123",
        )
        service.installation_units.add(unit)

        # Calculate revenue
        revenue = RevenueCalculator.calculate_service_revenue(service, save=False)

        # Main stall should get: labor (1000) + margin (7500) = 8500
        expected_main = Decimal("1000.00") + Decimal("7500.00")
        # Sub stall should get: cost (14500)
        expected_sub = Decimal("14500.00")

        self.assertEqual(revenue["main_revenue"], expected_main)
        self.assertEqual(revenue["sub_revenue"], expected_sub)
        self.assertEqual(
            revenue["total_revenue"], expected_main + expected_sub
        )

    def test_aircon_unit_with_promo_price(self):
        """Test aircon unit revenue split with promo price."""
        # Create model with promo price
        model_promo = AirconModel.objects.create(
            brand=self.brand,
            name="1.5 HP Promo",
            retail_price=Decimal("22000.00"),
            cost_price=Decimal("14500.00"),
            promo_price=Decimal("19000.00"),
        )

        service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            service_type=ServiceType.INSTALLATION,
        )

        appliance = ServiceAppliance.objects.create(
            service=service,
            appliance_type=self.appliance_type,
            labor_fee=Decimal("1000.00"),
        )

        unit = AirconUnit.objects.create(
            model=model_promo,
            serial_number="PROMO123",
        )
        service.installation_units.add(unit)

        revenue = RevenueCalculator.calculate_service_revenue(service, save=False)

        # Main: labor (1000) + margin (19000 - 14500 = 4500) = 5500
        # Sub: cost (14500)
        expected_main = Decimal("1000.00") + Decimal("4500.00")
        expected_sub = Decimal("14500.00")

        self.assertEqual(revenue["main_revenue"], expected_main)
        self.assertEqual(revenue["sub_revenue"], expected_sub)

    def test_multiple_aircon_units_revenue_split(self):
        """Test revenue split with multiple aircon units."""
        service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            service_type=ServiceType.INSTALLATION,
        )

        appliance = ServiceAppliance.objects.create(
            service=service,
            appliance_type=self.appliance_type,
            labor_fee=Decimal("2000.00"),
        )

        # Add 2 units
        unit1 = AirconUnit.objects.create(
            model=self.model,
            serial_number="UNIT001",
        )
        unit2 = AirconUnit.objects.create(
            model=self.model,
            serial_number="UNIT002",
        )
        service.installation_units.add(unit1, unit2)

        revenue = RevenueCalculator.calculate_service_revenue(service, save=False)

        # Main: labor (2000) + margins (2 × 7500) = 17000
        # Sub: costs (2 × 14500) = 29000
        expected_main = Decimal("2000.00") + (Decimal("7500.00") * 2)
        expected_sub = Decimal("14500.00") * 2

        self.assertEqual(revenue["main_revenue"], expected_main)
        self.assertEqual(revenue["sub_revenue"], expected_sub)

    def test_aircon_with_custom_unit_price_split(self):
        """Test revenue split when custom unit_price override is set."""
        service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            service_type=ServiceType.INSTALLATION,
        )

        # Custom price: 25000 (higher than selling price)
        appliance = ServiceAppliance.objects.create(
            service=service,
            appliance_type=self.appliance_type,
            labor_fee=Decimal("1000.00"),
            serial_number="CUSTOM001",
            unit_price=Decimal("25000.00"),
        )

        unit = AirconUnit.objects.create(
            model=self.model,
            serial_number="CUSTOM001",
        )
        service.installation_units.add(unit)

        revenue = RevenueCalculator.calculate_service_revenue(service, save=False)

        # Main: labor (1000) + margin (25000 - 14500 = 10500) = 11500
        # Sub: cost (14500)
        expected_main = Decimal("1000.00") + Decimal("10500.00")
        expected_sub = Decimal("14500.00")

        self.assertEqual(revenue["main_revenue"], expected_main)
        self.assertEqual(revenue["sub_revenue"], expected_sub)

    def test_aircon_unit_with_parts_revenue_allocation(self):
        """Test revenue split with both aircon units and parts."""
        service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            service_type=ServiceType.INSTALLATION,
        )

        appliance = ServiceAppliance.objects.create(
            service=service,
            appliance_type=self.appliance_type,
            labor_fee=Decimal("1000.00"),
        )

        # Add parts
        from services.models import ApplianceItemUsed

        ApplianceItemUsed.objects.create(
            appliance=appliance,
            item=self.capacitor,
            quantity=2,
            unit_price=Decimal("500.00"),
            stall_stock=self.capacitor_stock,
        )

        # Add aircon unit
        unit = AirconUnit.objects.create(
            model=self.model,
            serial_number="PARTS001",
        )
        service.installation_units.add(unit)

        revenue = RevenueCalculator.calculate_service_revenue(service, save=False)

        # Main: labor (1000) + margin (7500) = 8500
        # Sub: cost (14500) + parts (1000) = 15500
        expected_main = Decimal("1000.00") + Decimal("7500.00")
        expected_sub = Decimal("14500.00") + Decimal("1000.00")

        self.assertEqual(revenue["main_revenue"], expected_main)
        self.assertEqual(revenue["sub_revenue"], expected_sub)

    def test_installation_unit_additional_revenue_shifted_to_sub_stall(self):
        """Configured additional unit revenue should move from main to sub stall."""
        settings_obj = SystemSettings.get_settings()
        settings_obj.sub_stall_unit_revenue_additional = Decimal("2000.00")
        settings_obj.save(update_fields=["sub_stall_unit_revenue_additional"])

        service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            service_type=ServiceType.INSTALLATION,
        )

        ServiceAppliance.objects.create(
            service=service,
            appliance_type=self.appliance_type,
            labor_fee=Decimal("0.00"),
        )

        model_custom = AirconModel.objects.create(
            brand=self.brand,
            name="2.0 HP Additional",
            retail_price=Decimal("24000.00"),
            cost_price=Decimal("14500.00"),
            promo_price=None,
        )

        unit = AirconUnit.objects.create(
            model=model_custom,
            serial_number="ADD-SUB-001",
        )
        service.installation_units.add(unit)

        revenue = RevenueCalculator.calculate_service_revenue(service, save=False)

        self.assertEqual(revenue["sub_revenue"], Decimal("16500.00"))
        self.assertEqual(revenue["main_revenue"], Decimal("7500.00"))
        self.assertEqual(revenue["total_revenue"], Decimal("24000.00"))


class TestInstallationCompletionWithoutParts(AirconUnitAllocationTestSetup):
    """Test that installation services cannot be completed without parts configured."""

    def test_cannot_complete_installation_without_parts_validation(self):
        """
        Test that completion is blocked if installation service has units
        but no parts have been allocated.
        """
        from services.api.serializers import ServiceCompletionSerializer

        service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            service_type=ServiceType.INSTALLATION,
        )

        appliance = ServiceAppliance.objects.create(
            service=service,
            appliance_type=self.appliance_type,
            labor_fee=Decimal("1000.00"),
            status=ApplianceStatus.COMPLETED,
        )

        # Add installation unit but NO parts
        unit = AirconUnit.objects.create(
            model=self.model,
            serial_number="NOPARTS001",
        )
        service.installation_units.add(unit)

        # Try to complete service
        serializer = ServiceCompletionSerializer(
            data={},
            context={"service": service, "request": None},
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn(
            "without parts allocation",
            str(serializer.errors),
        )

    def test_can_complete_installation_with_parts(self):
        """
        Test that installation service CAN be completed if parts have been added.
        """
        from services.api.serializers import ServiceCompletionSerializer

        service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            service_type=ServiceType.INSTALLATION,
        )

        appliance = ServiceAppliance.objects.create(
            service=service,
            appliance_type=self.appliance_type,
            labor_fee=Decimal("1000.00"),
            status=ApplianceStatus.COMPLETED,
        )

        # Add installation unit
        unit = AirconUnit.objects.create(
            model=self.model,
            serial_number="WITHPARTS001",
        )
        service.installation_units.add(unit)

        # Add parts to appliance
        from services.models import ApplianceItemUsed

        ApplianceItemUsed.objects.create(
            appliance=appliance,
            item=self.capacitor,
            quantity=1,
            unit_price=Decimal("500.00"),
            stall_stock=self.capacitor_stock,
        )

        # Validate - should NOT have errors about parts allocation
        serializer = ServiceCompletionSerializer(
            data={},
            context={"service": service, "request": None},
        )

        # Should validate successfully for parts allocation
        # (may still have other validation issues, but not about missing parts)
        is_valid = serializer.is_valid()
        errors_str = str(serializer.errors)

        # Check that we don't get the "without parts allocation" error
        if not is_valid:
            self.assertNotIn(
                "without parts allocation",
                errors_str,
            )


class TestTransactionCreationWithSplit(AirconUnitAllocationTestSetup):
    """Test that transactions are created correctly with the split pricing."""

    def test_sub_stall_transaction_includes_aircon_cost(self):
        """
        Test that sub stall transaction includes the aircon unit cost price.
        """
        service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            service_type=ServiceType.INSTALLATION,
        )

        appliance = ServiceAppliance.objects.create(
            service=service,
            appliance_type=self.appliance_type,
            labor_fee=Decimal("1000.00"),
            status=ApplianceStatus.COMPLETED,
            items_checked=False,
        )

        # Add parts
        from services.models import ApplianceItemUsed

        ApplianceItemUsed.objects.create(
            appliance=appliance,
            item=self.capacitor,
            quantity=1,
            unit_price=Decimal("500.00"),
            stall_stock=self.capacitor_stock,
        )

        # Add aircon unit
        unit = AirconUnit.objects.create(
            model=self.model,
            serial_number="TXTEST001",
        )
        service.installation_units.add(unit)

        # Complete service
        ServiceCompletionHandler.complete_service(
            service=service,
            user=self.user,
            create_receipt=True,
        )

        service.refresh_from_db()

        # Check sub stall transaction
        sub_tx = service.related_sub_transaction
        self.assertIsNotNone(sub_tx)

        # Should have 2 items: capacitor (500) + aircon cost (14500)
        items = list(sub_tx.items.all())
        self.assertEqual(len(items), 2)

        # Find and verify capacitor item
        cap_item = next((i for i in items if i.item == self.capacitor), None)
        self.assertIsNotNone(cap_item)
        self.assertEqual(cap_item.final_price_per_unit, Decimal("500.00"))

        # Find and verify aircon cost item
        aircon_item = next(
            (i for i in items if "Aircon Unit Cost" in i.description), None
        )
        self.assertIsNotNone(aircon_item)
        self.assertEqual(aircon_item.final_price_per_unit, Decimal("14500.00"))

    def test_main_stall_transaction_includes_aircon_margin(self):
        """
        Test that main stall transaction includes only the aircon margin.
        """
        service = Service.objects.create(
            client=self.client_obj,
            stall=self.main_stall,
            service_type=ServiceType.INSTALLATION,
        )

        appliance = ServiceAppliance.objects.create(
            service=service,
            appliance_type=self.appliance_type,
            labor_fee=Decimal("1000.00"),
            status=ApplianceStatus.COMPLETED,
            items_checked=False,
        )

        # Add parts
        from services.models import ApplianceItemUsed

        ApplianceItemUsed.objects.create(
            appliance=appliance,
            item=self.capacitor,
            quantity=1,
            unit_price=Decimal("500.00"),
            stall_stock=self.capacitor_stock,
        )

        # Add aircon unit
        unit = AirconUnit.objects.create(
            model=self.model,
            serial_number="TXMAIN001",
        )
        service.installation_units.add(unit)

        # Complete service
        ServiceCompletionHandler.complete_service(
            service=service,
            user=self.user,
            create_receipt=True,
        )

        service.refresh_from_db()

        # Check main stall transaction
        main_tx = service.related_transaction
        self.assertIsNotNone(main_tx)

        # Should have 2 items: labor (1000) + aircon margin (7500)
        items = list(main_tx.items.all())
        self.assertEqual(len(items), 2)

        # Find and verify labor item
        labor_item = next((i for i in items if "Labor" in i.description), None)
        self.assertIsNotNone(labor_item)
        self.assertEqual(labor_item.final_price_per_unit, Decimal("1000.00"))

        # Find and verify aircon margin item
        aircon_item = next(
            (i for i in items if "Aircon Unit" in i.description and "Cost" not in i.description), None
        )
        self.assertIsNotNone(aircon_item)
        self.assertEqual(aircon_item.final_price_per_unit, Decimal("7500.00"))

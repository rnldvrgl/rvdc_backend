"""
Comprehensive tests for warranty management and free cleaning system.

Test Coverage:
- Warranty eligibility checking
- Warranty claim creation and lifecycle
- Warranty claim approval/rejection
- Warranty service creation
- Free cleaning redemption
- Business logic validation
"""

from datetime import date, timedelta
from decimal import Decimal

from clients.models import Client
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from inventory.models import Stall
from rest_framework.exceptions import ValidationError
from sales.models import SalesTransaction
from utils.enums import ServiceType

from installations.business_logic import (
    FreeCleaningManager,
    WarrantyClaimManager,
    WarrantyEligibilityChecker,
    WarrantyServiceHandler,
)
from installations.models import (
    AirconBrand,
    AirconModel,
    AirconUnit,
    WarrantyClaim,
)

User = get_user_model()


class WarrantyEligibilityTestCase(TestCase):
    """Test warranty eligibility checking."""

    def setUp(self):
        """Set up test data."""
        # Create main stall
        self.main_stall = Stall.objects.create(
            name="Main Stall",
            stall_type="main",
            is_system=True,
        )

        # Create client
        self.client = Client.objects.create(
            name="John Doe",
            email="john@example.com",
            contact_number="09123456789",
        )

        # Create aircon model
        self.brand = AirconBrand.objects.create(name="Samsung")
        self.model = AirconModel.objects.create(
            brand=self.brand,
            name="AR12",
            retail_price=Decimal("25000.00"),
            aircon_type="split",
        )

        # Create sold unit with active warranty
        self.active_unit = AirconUnit.objects.create(
            model=self.model,
            serial_number="SN001",
            stall=self.main_stall,
            is_sold=True,
            warranty_start_date=date.today() - timedelta(days=30),
            warranty_period_months=12,
        )

        # Create sale transaction
        self.sale = SalesTransaction.objects.create(
            client=self.client,
            stall=self.main_stall,
            total_price=Decimal("25000.00"),
        )
        self.active_unit.sale = self.sale
        self.active_unit.save()

    def test_eligible_unit(self):
        """Test that a valid unit under warranty is eligible."""
        result = WarrantyEligibilityChecker.check_eligibility(self.active_unit)

        self.assertTrue(result['eligible'])
        self.assertIn('under warranty', result['reason'].lower())
        self.assertGreater(result['warranty_days_left'], 0)

    def test_not_sold_unit(self):
        """Test that unsold unit is not eligible."""
        unsold_unit = AirconUnit.objects.create(
            model=self.model,
            serial_number="SN002",
            stall=self.main_stall,
            is_sold=False,
        )

        result = WarrantyEligibilityChecker.check_eligibility(unsold_unit)

        self.assertFalse(result['eligible'])
        self.assertIn('not been sold', result['reason'].lower())

    def test_no_warranty_unit(self):
        """Test that unit with no warranty is not eligible."""
        no_warranty_unit = AirconUnit.objects.create(
            model=self.model,
            serial_number="SN003",
            stall=self.main_stall,
            is_sold=True,
            warranty_period_months=0,
        )
        no_warranty_unit.sale = self.sale
        no_warranty_unit.save()

        result = WarrantyEligibilityChecker.check_eligibility(no_warranty_unit)

        self.assertFalse(result['eligible'])
        self.assertIn('no warranty', result['reason'].lower())

    def test_expired_warranty_unit(self):
        """Test that unit with expired warranty is not eligible."""
        expired_unit = AirconUnit.objects.create(
            model=self.model,
            serial_number="SN004",
            stall=self.main_stall,
            is_sold=True,
            warranty_start_date=date.today() - timedelta(days=400),
            warranty_period_months=12,
        )
        expired_unit.sale = self.sale
        expired_unit.save()

        result = WarrantyEligibilityChecker.check_eligibility(expired_unit)

        self.assertFalse(result['eligible'])
        self.assertIn('expired', result['reason'].lower())

    def test_warranty_not_started(self):
        """Test that unit with no start date is not eligible."""
        not_started_unit = AirconUnit.objects.create(
            model=self.model,
            serial_number="SN005",
            stall=self.main_stall,
            is_sold=True,
            warranty_start_date=None,
            warranty_period_months=12,
        )
        not_started_unit.sale = self.sale
        not_started_unit.save()

        result = WarrantyEligibilityChecker.check_eligibility(not_started_unit)

        self.assertFalse(result['eligible'])
        self.assertIn('not started', result['reason'].lower())


class WarrantyClaimCreationTestCase(TestCase):
    """Test warranty claim creation."""

    def setUp(self):
        """Set up test data."""
        # Create main stall
        self.main_stall = Stall.objects.create(
            name="Main Stall",
            stall_type="main",
            is_system=True,
        )

        # Create client
        self.client = Client.objects.create(
            name="Jane Smith",
            email="jane@example.com",
            contact_number="09987654321",
        )

        # Create aircon model
        self.brand = AirconBrand.objects.create(name="LG")
        self.model = AirconModel.objects.create(
            brand=self.brand,
            name="LS-H126",
            retail_price=Decimal("30000.00"),
            aircon_type="split",
        )

        # Create sold unit with warranty
        self.unit = AirconUnit.objects.create(
            model=self.model,
            serial_number="SN100",
            stall=self.main_stall,
            is_sold=True,
            warranty_start_date=date.today() - timedelta(days=60),
            warranty_period_months=12,
        )

        self.sale = SalesTransaction.objects.create(
            client=self.client,
            stall=self.main_stall,
            total_price=Decimal("30000.00"),
        )
        self.unit.sale = self.sale
        self.unit.save()

    def test_create_warranty_claim(self):
        """Test creating a warranty claim."""
        claim = WarrantyClaimManager.create_claim(
            unit=self.unit,
            issue_description="Unit not cooling properly",
            claim_type="repair",
            customer_notes="Issue started last week",
        )

        self.assertIsNotNone(claim)
        self.assertEqual(claim.unit, self.unit)
        self.assertEqual(claim.status, WarrantyClaim.ClaimStatus.PENDING)
        self.assertEqual(claim.claim_type, "repair")
        self.assertTrue(claim.is_valid_claim)
        self.assertTrue(claim.is_pending)

    def test_create_claim_ineligible_unit(self):
        """Test that creating claim for ineligible unit fails."""
        # Create expired unit
        expired_unit = AirconUnit.objects.create(
            model=self.model,
            serial_number="SN101",
            stall=self.main_stall,
            is_sold=True,
            warranty_start_date=date.today() - timedelta(days=400),
            warranty_period_months=12,
        )
        expired_unit.sale = self.sale
        expired_unit.save()

        with self.assertRaises(ValidationError):
            WarrantyClaimManager.create_claim(
                unit=expired_unit,
                issue_description="Not working",
            )

    def test_multiple_claims_allowed(self):
        """Test that multiple claims can be created for same unit."""
        claim1 = WarrantyClaimManager.create_claim(
            unit=self.unit,
            issue_description="First issue",
        )

        claim2 = WarrantyClaimManager.create_claim(
            unit=self.unit,
            issue_description="Second issue",
        )

        self.assertNotEqual(claim1.id, claim2.id)
        self.assertEqual(self.unit.warranty_claims.count(), 2)


class WarrantyClaimApprovalTestCase(TestCase):
    """Test warranty claim approval workflow."""

    def setUp(self):
        """Set up test data."""
        # Create user for approval
        self.reviewer = User.objects.create_user(
            username="reviewer",
            email="reviewer@example.com",
            password="testpass123",
            role="admin",
        )

        # Create main stall
        self.main_stall = Stall.objects.create(
            name="Main Stall",
            stall_type="main",
            is_system=True,
        )

        # Create client
        self.client = Client.objects.create(
            name="Test Client",
            email="client@example.com",
            contact_number="09111111111",
        )

        # Create aircon
        self.brand = AirconBrand.objects.create(name="Panasonic")
        self.model = AirconModel.objects.create(
            brand=self.brand,
            name="CU-Z12",
            retail_price=Decimal("28000.00"),
            aircon_type="split",
        )

        self.unit = AirconUnit.objects.create(
            model=self.model,
            serial_number="SN200",
            stall=self.main_stall,
            is_sold=True,
            warranty_start_date=date.today() - timedelta(days=45),
            warranty_period_months=12,
        )

        self.sale = SalesTransaction.objects.create(
            client=self.client,
            stall=self.main_stall,
            total_price=Decimal("28000.00"),
        )
        self.unit.sale = self.sale
        self.unit.save()

        # Create pending claim
        self.claim = WarrantyClaimManager.create_claim(
            unit=self.unit,
            issue_description="Compressor making noise",
        )

    def test_approve_claim(self):
        """Test approving a warranty claim."""
        result = WarrantyClaimManager.approve_claim(
            claim=self.claim,
            reviewed_by=self.reviewer,
            technician_assessment="Compressor needs replacement",
            create_service=False,
        )

        claim = result['claim']

        self.assertEqual(claim.status, WarrantyClaim.ClaimStatus.APPROVED)
        self.assertEqual(claim.reviewed_by, self.reviewer)
        self.assertIsNotNone(claim.reviewed_at)
        self.assertTrue(claim.is_valid_claim)
        self.assertTrue(claim.is_approved)

    def test_approve_claim_with_service(self):
        """Test approving claim and creating service."""
        result = WarrantyClaimManager.approve_claim(
            claim=self.claim,
            reviewed_by=self.reviewer,
            create_service=True,
        )

        claim = result['claim']
        service = result.get('service')

        self.assertEqual(claim.status, WarrantyClaim.ClaimStatus.APPROVED)
        self.assertIsNotNone(service)
        self.assertEqual(claim.service, service)
        self.assertEqual(service.client, self.client)
        self.assertEqual(service.stall, self.main_stall)

    def test_approve_non_pending_claim_fails(self):
        """Test that approving non-pending claim fails."""
        # Approve first time
        WarrantyClaimManager.approve_claim(
            claim=self.claim,
            reviewed_by=self.reviewer,
            create_service=False,
        )

        # Try to approve again
        with self.assertRaises(ValidationError):
            WarrantyClaimManager.approve_claim(
                claim=self.claim,
                reviewed_by=self.reviewer,
            )


class WarrantyClaimRejectionTestCase(TestCase):
    """Test warranty claim rejection workflow."""

    def setUp(self):
        """Set up test data."""
        self.reviewer = User.objects.create_user(
            username="reviewer2",
            email="reviewer2@example.com",
            password="testpass123",
            role="admin",
        )

        self.main_stall = Stall.objects.create(
            name="Main Stall",
            stall_type="main",
            is_system=True,
        )

        self.client = Client.objects.create(
            name="Client 2",
            email="client2@example.com",
            contact_number="09222222222",
        )

        self.brand = AirconBrand.objects.create(name="Daikin")
        self.model = AirconModel.objects.create(
            brand=self.brand,
            name="FTK-35",
            retail_price=Decimal("32000.00"),
            aircon_type="wall_mounted",
        )

        self.unit = AirconUnit.objects.create(
            model=self.model,
            serial_number="SN300",
            stall=self.main_stall,
            is_sold=True,
            warranty_start_date=date.today() - timedelta(days=90),
            warranty_period_months=12,
        )

        self.sale = SalesTransaction.objects.create(
            client=self.client,
            stall=self.main_stall,
            total_price=Decimal("32000.00"),
        )
        self.unit.sale = self.sale
        self.unit.save()

        self.claim = WarrantyClaimManager.create_claim(
            unit=self.unit,
            issue_description="Unit leaking water",
        )

    def test_reject_claim(self):
        """Test rejecting a warranty claim."""
        claim = WarrantyClaimManager.reject_claim(
            claim=self.claim,
            reviewed_by=self.reviewer,
            rejection_reason="Damage caused by improper installation",
            is_valid_claim=False,
        )

        self.assertEqual(claim.status, WarrantyClaim.ClaimStatus.REJECTED)
        self.assertEqual(claim.reviewed_by, self.reviewer)
        self.assertIsNotNone(claim.reviewed_at)
        self.assertIn("improper installation", claim.rejection_reason)
        self.assertFalse(claim.is_valid_claim)

    def test_reject_without_reason_fails(self):
        """Test that rejecting without reason fails."""
        with self.assertRaises(ValidationError):
            WarrantyClaimManager.reject_claim(
                claim=self.claim,
                reviewed_by=self.reviewer,
                rejection_reason="",
            )


class WarrantyServiceCreationTestCase(TestCase):
    """Test warranty service creation."""

    def setUp(self):
        """Set up test data."""
        self.main_stall = Stall.objects.create(
            name="Main Stall",
            stall_type="main",
            is_system=True,
        )

        self.client = Client.objects.create(
            name="Service Client",
            email="service@example.com",
            contact_number="09333333333",
        )

        self.brand = AirconBrand.objects.create(name="Carrier")
        self.model = AirconModel.objects.create(
            brand=self.brand,
            name="42KQV025",
            retail_price=Decimal("35000.00"),
            aircon_type="split",
        )

        self.unit = AirconUnit.objects.create(
            model=self.model,
            serial_number="SN400",
            stall=self.main_stall,
            is_sold=True,
            warranty_start_date=date.today() - timedelta(days=120),
            warranty_period_months=12,
        )

        self.sale = SalesTransaction.objects.create(
            client=self.client,
            stall=self.main_stall,
            total_price=Decimal("35000.00"),
        )
        self.unit.sale = self.sale
        self.unit.save()

        self.claim = WarrantyClaimManager.create_claim(
            unit=self.unit,
            issue_description="Unit not starting",
            claim_type="repair",
        )

        # Approve claim first
        self.reviewer = User.objects.create_user(
            username="reviewer3",
            email="reviewer3@example.com",
            password="testpass123",
        )
        WarrantyClaimManager.approve_claim(
            claim=self.claim,
            reviewed_by=self.reviewer,
            create_service=False,
        )
        self.claim.refresh_from_db()

    def test_create_warranty_service(self):
        """Test creating a warranty service."""
        service = WarrantyServiceHandler.create_warranty_service(
            claim=self.claim,
        )

        self.assertIsNotNone(service)
        self.assertEqual(service.client, self.client)
        self.assertEqual(service.stall, self.main_stall)
        self.assertEqual(service.service_type, ServiceType.REPAIR)
        self.assertIn("WARRANTY CLAIM", service.description)
        self.assertEqual(self.claim.service, service)
        self.assertEqual(self.claim.status, WarrantyClaim.ClaimStatus.IN_PROGRESS)

    def test_create_service_with_scheduling(self):
        """Test creating service with scheduled date/time."""
        scheduled_date = date.today() + timedelta(days=3)
        scheduled_time = timezone.now().time()

        service = WarrantyServiceHandler.create_warranty_service(
            claim=self.claim,
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time,
        )

        self.assertEqual(service.scheduled_date, scheduled_date)
        self.assertEqual(service.scheduled_time, scheduled_time)

    def test_create_service_for_inspection_claim(self):
        """Test creating inspection service for inspection claim."""
        inspection_claim = WarrantyClaimManager.create_claim(
            unit=self.unit,
            issue_description="Need inspection",
            claim_type="inspection",
        )

        WarrantyClaimManager.approve_claim(
            claim=inspection_claim,
            reviewed_by=self.reviewer,
            create_service=False,
        )
        inspection_claim.refresh_from_db()

        service = WarrantyServiceHandler.create_warranty_service(
            claim=inspection_claim,
        )

        self.assertEqual(service.service_type, ServiceType.CHECK_UP)


class FreeCleaningEligibilityTestCase(TestCase):
    """Test free cleaning eligibility."""

    def setUp(self):
        """Set up test data."""
        self.main_stall = Stall.objects.create(
            name="Main Stall",
            stall_type="main",
            is_system=True,
        )

        self.client = Client.objects.create(
            name="Cleaning Client",
            email="cleaning@example.com",
            contact_number="09444444444",
        )

        self.brand = AirconBrand.objects.create(name="Fujitsu")
        self.model = AirconModel.objects.create(
            brand=self.brand,
            name="ASYG12",
            retail_price=Decimal("27000.00"),
            aircon_type="split",
        )

        self.unit = AirconUnit.objects.create(
            model=self.model,
            serial_number="SN500",
            stall=self.main_stall,
            is_sold=True,
            warranty_start_date=date.today() - timedelta(days=30),
            warranty_period_months=12,
            free_cleaning_redeemed=False,
        )

        self.sale = SalesTransaction.objects.create(
            client=self.client,
            stall=self.main_stall,
            total_price=Decimal("27000.00"),
        )
        self.unit.sale = self.sale
        self.unit.save()

    def test_eligible_for_free_cleaning(self):
        """Test eligible unit for free cleaning."""
        result = FreeCleaningManager.check_eligibility(self.unit)

        self.assertTrue(result['eligible'])
        self.assertIn('eligible', result['reason'].lower())

    def test_already_redeemed(self):
        """Test unit that already redeemed cleaning."""
        self.unit.free_cleaning_redeemed = True
        self.unit.save()

        result = FreeCleaningManager.check_eligibility(self.unit)

        self.assertFalse(result['eligible'])
        self.assertIn('already been redeemed', result['reason'].lower())

    def test_not_sold_unit(self):
        """Test unsold unit not eligible."""
        unsold_unit = AirconUnit.objects.create(
            model=self.model,
            serial_number="SN501",
            stall=self.main_stall,
            is_sold=False,
        )

        result = FreeCleaningManager.check_eligibility(unsold_unit)

        self.assertFalse(result['eligible'])
        self.assertIn('not been sold', result['reason'].lower())

    def test_expired_warranty(self):
        """Test expired warranty unit not eligible."""
        self.unit.warranty_start_date = date.today() - timedelta(days=400)
        self.unit.save()

        result = FreeCleaningManager.check_eligibility(self.unit)

        self.assertFalse(result['eligible'])
        self.assertIn('no longer under warranty', result['reason'].lower())


class FreeCleaningRedemptionTestCase(TestCase):
    """Test free cleaning redemption."""

    def setUp(self):
        """Set up test data."""
        self.main_stall = Stall.objects.create(
            name="Main Stall",
            stall_type="main",
            is_system=True,
        )

        self.client = Client.objects.create(
            name="Redemption Client",
            email="redeem@example.com",
            contact_number="09555555555",
        )

        self.brand = AirconBrand.objects.create(name="Mitsubishi")
        self.model = AirconModel.objects.create(
            brand=self.brand,
            name="MS-GK10",
            retail_price=Decimal("29000.00"),
            aircon_type="split",
        )

        self.unit = AirconUnit.objects.create(
            model=self.model,
            serial_number="SN600",
            stall=self.main_stall,
            is_sold=True,
            warranty_start_date=date.today() - timedelta(days=60),
            warranty_period_months=12,
            free_cleaning_redeemed=False,
        )

        self.sale = SalesTransaction.objects.create(
            client=self.client,
            stall=self.main_stall,
            total_price=Decimal("29000.00"),
        )
        self.unit.sale = self.sale
        self.unit.save()

    def test_redeem_free_cleaning(self):
        """Test redeeming free cleaning."""
        result = FreeCleaningManager.redeem_free_cleaning(
            unit=self.unit,
        )

        service = result['service']
        unit = result['unit']

        self.assertIsNotNone(service)
        self.assertEqual(service.service_type, ServiceType.CLEANING)
        self.assertEqual(service.client, self.client)
        self.assertEqual(service.stall, self.main_stall)
        self.assertIn("FREE CLEANING", service.description)
        self.assertTrue(unit.free_cleaning_redeemed)

    def test_redeem_with_scheduling(self):
        """Test redeeming with scheduled date/time."""
        scheduled_date = date.today() + timedelta(days=7)
        scheduled_time = timezone.now().time()

        result = FreeCleaningManager.redeem_free_cleaning(
            unit=self.unit,
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time,
        )

        service = result['service']

        self.assertEqual(service.scheduled_date, scheduled_date)
        self.assertEqual(service.scheduled_time, scheduled_time)

    def test_redeem_already_redeemed_fails(self):
        """Test that redeeming twice fails."""
        # First redemption
        FreeCleaningManager.redeem_free_cleaning(unit=self.unit)

        # Try again
        with self.assertRaises(ValidationError):
            FreeCleaningManager.redeem_free_cleaning(unit=self.unit)

    def test_unredeemed_units_query(self):
        """Test getting unredeemed units."""
        # Create another unit that hasn't redeemed
        unit2 = AirconUnit.objects.create(
            model=self.model,
            serial_number="SN601",
            stall=self.main_stall,
            is_sold=True,
            warranty_start_date=date.today() - timedelta(days=30),
            warranty_period_months=12,
            free_cleaning_redeemed=False,
        )
        unit2.sale = self.sale
        unit2.save()

        # Redeem one unit
        FreeCleaningManager.redeem_free_cleaning(unit=self.unit)

        # Query unredeemed units
        unredeemed = FreeCleaningManager.unredeemed_units()

        self.assertEqual(unredeemed.count(), 1)
        self.assertIn(unit2, unredeemed)
        self.assertNotIn(self.unit, unredeemed)

    def test_unredeemed_units_by_client(self):
        """Test getting unredeemed units for specific client."""
        # Create another client with a unit
        other_client = Client.objects.create(
            name="Other Client",
            email="other@example.com",
            contact_number="09666666666",
        )

        other_sale = SalesTransaction.objects.create(
            client=other_client,
            stall=self.main_stall,
            total_price=Decimal("29000.00"),
        )

        other_unit = AirconUnit.objects.create(
            model=self.model,
            serial_number="SN602",
            stall=self.main_stall,
            is_sold=True,
            warranty_start_date=date.today() - timedelta(days=30),
            warranty_period_months=12,
            free_cleaning_redeemed=False,
        )
        other_unit.sale = other_sale
        other_unit.save()

        # Query unredeemed for specific client
        unredeemed = FreeCleaningManager.unredeemed_units(client=self.client)

        self.assertEqual(unredeemed.count(), 1)
        self.assertIn(self.unit, unredeemed)
        self.assertNotIn(other_unit, unredeemed)


class WarrantyClaimCompleteTestCase(TestCase):
    """Test warranty claim completion."""

    def setUp(self):
        """Set up test data."""
        self.main_stall = Stall.objects.create(
            name="Main Stall",
            stall_type="main",
            is_system=True,
        )

        self.client = Client.objects.create(
            name="Complete Client",
            email="complete@example.com",
            contact_number="09777777777",
        )

        self.reviewer = User.objects.create_user(
            username="reviewer4",
            email="reviewer4@example.com",
            password="testpass123",
        )

        self.brand = AirconBrand.objects.create(name="York")
        self.model = AirconModel.objects.create(
            brand=self.brand,
            name="YC12",
            retail_price=Decimal("26000.00"),
            aircon_type="window",
        )

        self.unit = AirconUnit.objects.create(
            model=self.model,
            serial_number="SN700",
            stall=self.main_stall,
            is_sold=True,
            warranty_start_date=date.today() - timedelta(days=150),
            warranty_period_months=12,
        )

        self.sale = SalesTransaction.objects.create(
            client=self.client,
            stall=self.main_stall,
            total_price=Decimal("26000.00"),
        )
        self.unit.sale = self.sale
        self.unit.save()

        # Create and approve claim with service
        self.claim = WarrantyClaimManager.create_claim(
            unit=self.unit,
            issue_description="Fan not working",
        )

        result = WarrantyClaimManager.approve_claim(
            claim=self.claim,
            reviewed_by=self.reviewer,
            create_service=True,
        )
        self.claim.refresh_from_db()
        self.service = result['service']

    def test_complete_claim_without_service_completion_fails(self):
        """Test that completing claim before service fails."""
        with self.assertRaises(ValidationError):
            WarrantyClaimManager.complete_claim(self.claim)

    def test_complete_claim_after_service_completion(self):
        """Test completing claim after service is done."""
        # Complete the service first
        self.service.status = 'completed'
        self.service.save()

        # Now complete the claim
        claim = WarrantyClaimManager.complete_claim(self.claim)

        self.assertEqual(claim.status, WarrantyClaim.ClaimStatus.COMPLETED)
        self.assertIsNotNone(claim.completed_at)

    def test_complete_already_completed_fails(self):
        """Test that completing twice fails."""
        # Complete service
        self.service.status = 'completed'
        self.service.save()

        # Complete claim first time
        WarrantyClaimManager.complete_claim(self.claim)

        # Try again
        self.claim.refresh_from_db()
        with self.assertRaises(ValidationError):
            WarrantyClaimManager.complete_claim(self.claim)


class WarrantyClaimCancelTestCase(TestCase):
    """Test warranty claim cancellation."""

    def setUp(self):
        """Set up test data."""
        self.main_stall = Stall.objects.create(
            name="Main Stall",
            stall_type="main",
            is_system=True,
        )

        self.client = Client.objects.create(
            name="Cancel Client",
            email="cancel@example.com",
            contact_number="09888888888",
        )

        self.brand = AirconBrand.objects.create(name="Toshiba")
        self.model = AirconModel.objects.create(
            brand=self.brand,
            name="RAS-10",
            retail_price=Decimal("24000.00"),
            aircon_type="split",
        )

        self.unit = AirconUnit.objects.create(
            model=self.model,
            serial_number="SN800",
            stall=self.main_stall,
            is_sold=True,
            warranty_start_date=date.today() - timedelta(days=45),
            warranty_period_months=12,
        )

        self.sale = SalesTransaction.objects.create(
            client=self.client,
            stall=self.main_stall,
            total_price=Decimal("24000.00"),
        )
        self.unit.sale = self.sale
        self.unit.save()

        self.claim = WarrantyClaimManager.create_claim(
            unit=self.unit,
            issue_description="Strange odor",
        )

    def test_cancel_pending_claim(self):
        """Test cancelling a pending claim."""
        claim = WarrantyClaimManager.cancel_claim(
            claim=self.claim,
            cancellation_reason="Customer changed mind",
        )

        self.assertEqual(claim.status, WarrantyClaim.ClaimStatus.CANCELLED)
        self.assertIn("changed mind", claim.customer_notes)

    def test_cancel_already_cancelled_fails(self):
        """Test that cancelling twice fails."""
        WarrantyClaimManager.cancel_claim(claim=self.claim)

        self.claim.refresh_from_db()
        with self.assertRaises(ValidationError):
            WarrantyClaimManager.cancel_claim(claim=self.claim)

    def test_cancel_completed_claim_fails(self):
        """Test that cancelling completed claim fails."""
        # Force complete status (skip normal workflow for test)
        self.claim.status = WarrantyClaim.ClaimStatus.COMPLETED
        self.claim.save()

        with self.assertRaises(ValidationError):
            WarrantyClaimManager.cancel_claim(claim=self.claim)

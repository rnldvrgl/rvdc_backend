#!/usr/bin/env python
"""
Quick test script for installation service unit price integration.
Run this in Django shell: python manage.py shell < test_installation_units.py
Or: python manage.py shell
Then: exec(open('test_installation_units.py').read())
"""

print("=" * 60)
print("INSTALLATION UNIT PRICE INTEGRATION - TEST SCRIPT")
print("=" * 60)

from decimal import Decimal
from django.utils import timezone
from installations.models import AirconBrand, AirconModel, AirconUnit
from inventory.models import Stall
from clients.models import Client
from services.models import Service, ServiceAppliance
from sales.models import SalesTransaction, SalesItem
from users.models import CustomUser

# Color codes for terminal
class Colors:
    PASS = '\033[92m'  # Green
    FAIL = '\033[91m'  # Red
    INFO = '\033[94m'  # Blue
    WARN = '\033[93m'  # Yellow
    END = '\033[0m'    # Reset

def test_result(passed, message):
    if passed:
        print(f"{Colors.PASS}✓ PASS{Colors.END}: {message}")
        return True
    else:
        print(f"{Colors.FAIL}✗ FAIL{Colors.END}: {message}")
        return False

def info(message):
    print(f"{Colors.INFO}ℹ{Colors.END} {message}")

def warn(message):
    print(f"{Colors.WARN}⚠{Colors.END} {message}")

# Test counters
total_tests = 0
passed_tests = 0

print("\n" + "=" * 60)
print("TEST 1: CHECK PREREQUISITES")
print("=" * 60)

# Test 1.1: Check stalls
total_tests += 1
main_stall = Stall.objects.filter(stall_type='main', is_system=True).first()
sub_stall = Stall.objects.filter(stall_type='sub', is_system=True).first()
if test_result(main_stall and sub_stall, "System stalls configured"):
    passed_tests += 1
    info(f"Main Stall: {main_stall.name}")
    info(f"Sub Stall: {sub_stall.name}")
else:
    warn("Run: python manage.py setup_stalls")

# Test 1.2: Check aircon models
total_tests += 1
models_count = AirconModel.objects.count()
if test_result(models_count > 0, f"Aircon models exist ({models_count} found)"):
    passed_tests += 1
    sample_model = AirconModel.objects.first()
    info(f"Sample: {sample_model.brand.name} {sample_model.name}")
    info(f"  Retail: ₱{sample_model.retail_price}, Promo: ₱{sample_model.promo_price}")

# Test 1.3: Check available units
total_tests += 1
available_units = AirconUnit.objects.filter(
    sale__isnull=True,
    reserved_by__isnull=True,
    is_sold=False
).count()
if test_result(available_units > 0, f"Available units exist ({available_units} found)"):
    passed_tests += 1
else:
    warn("Create test units using the guide")

# Test 1.4: Check clients
total_tests += 1
clients_count = Client.objects.count()
if test_result(clients_count > 0, f"Clients exist ({clients_count} found)"):
    passed_tests += 1

print("\n" + "=" * 60)
print("TEST 2: SERIALIZER VERIFICATION")
print("=" * 60)

# Test 2.1: Check AirconModelSerializer includes promo_price
total_tests += 1
try:
    from installations.api.serializers import AirconModelSerializer
    serializer_fields = AirconModelSerializer.Meta.fields
    has_promo = 'promo_price' in serializer_fields
    if test_result(has_promo, "AirconModelSerializer includes promo_price"):
        passed_tests += 1
    else:
        warn("Add 'promo_price' to AirconModelSerializer.Meta.fields")
except Exception as e:
    test_result(False, f"Check AirconModelSerializer: {e}")

# Test 2.2: Check ServiceSerializer includes installation_units
total_tests += 1
try:
    from services.api.serializers import ServiceSerializer
    serializer = ServiceSerializer()
    has_units = 'installation_units' in serializer.fields
    if test_result(has_units, "ServiceSerializer includes installation_units"):
        passed_tests += 1
except Exception as e:
    test_result(False, f"Check ServiceSerializer: {e}")

print("\n" + "=" * 60)
print("TEST 3: REVENUE CALCULATION")
print("=" * 60)

# Test 3.1: Find an installation service with units
total_tests += 1
test_service = Service.objects.filter(
    service_type='installation',
    installation_units__isnull=False
).distinct().first()

if test_service:
    info(f"Testing with Service #{test_service.id}")
    
    # Get expected revenue
    labor_sum = sum(
        float(a.discounted_labor_fee or a.labor_fee)
        for a in test_service.appliances.all()
        if not a.labor_is_free
    )
    
    units_sum = sum(
        float(u.model.promo_price)
        for u in test_service.installation_units.all()
        if u.model
    )
    
    # Calculate parts sum from items_used (total_parts_cost is a serializer field, not model property)
    parts_sum = sum(
        float(item.line_total)
        for a in test_service.appliances.all()
        for item in a.items_used.all()
    )
    
    expected_main = Decimal(str(labor_sum + units_sum))
    expected_sub = Decimal(str(parts_sum))
    expected_total = expected_main + expected_sub
    
    actual_main = test_service.main_stall_revenue
    actual_sub = test_service.sub_stall_revenue
    actual_total = test_service.total_revenue
    
    info(f"Labor: ₱{labor_sum:,.2f}")
    info(f"Units: ₱{units_sum:,.2f}")
    info(f"Parts: ₱{parts_sum:,.2f}")
    info(f"Expected - Main: ₱{expected_main:,.2f}, Sub: ₱{expected_sub:,.2f}, Total: ₱{expected_total:,.2f}")
    info(f"Actual   - Main: ₱{actual_main:,.2f}, Sub: ₱{actual_sub:,.2f}, Total: ₱{actual_total:,.2f}")
    
    # Allow small rounding differences
    tolerance = Decimal('0.10')
    revenue_matches = (
        abs(actual_main - expected_main) < tolerance and
        abs(actual_sub - expected_sub) < tolerance and
        abs(actual_total - expected_total) < tolerance
    )
    
    if test_result(revenue_matches, "Revenue calculation includes unit prices"):
        passed_tests += 1
    else:
        warn("Run: python manage.py recalculate_service_revenue --installations-only")
else:
    warn("No installation services with units found. Create one to test.")

print("\n" + "=" * 60)
print("TEST 4: SALES TRANSACTION VERIFICATION")
print("=" * 60)

# Test 4.1: Check completed installation service has unit prices in sales
total_tests += 1
completed_service = Service.objects.filter(
    service_type='installation',
    status='completed',
    related_transaction__isnull=False,
    installation_units__isnull=False
).distinct().first()

if completed_service:
    info(f"Testing Service #{completed_service.id}")
    
    main_tx = completed_service.related_transaction
    labor_items = main_tx.items.filter(item__isnull=True, description__icontains='Labor').count()
    unit_items = main_tx.items.filter(item__isnull=True, description__icontains='Aircon Unit').count()
    
    info(f"Sales Items - Labor: {labor_items}, Units: {unit_items}")
    
    expected_units = completed_service.installation_units.count()
    has_unit_items = unit_items == expected_units
    
    if test_result(has_unit_items, f"Sales transaction includes {expected_units} unit item(s)"):
        passed_tests += 1
        
        # Show breakdown
        info("Sales Items Breakdown:")
        for item in main_tx.items.all():
            info(f"  - {item.description}: ₱{item.final_price_per_unit:,.2f} × {item.quantity}")
        info(f"  Total: ₱{main_tx.computed_total:,.2f}")
    else:
        warn("Complete a new installation service to test current implementation")
else:
    warn("No completed installation services found. Complete one to test.")

print("\n" + "=" * 60)
print("TEST 5: UNIT LINKING AND RESERVATION")
print("=" * 60)

# Test 5.1: Check if units are properly linked
total_tests += 1
if test_service:
    units = test_service.installation_units.all()
    all_linked = all(
        u.installation_service_id == test_service.id and
        u.reserved_by_id == test_service.client_id
        for u in units
    )
    
    if test_result(all_linked, "All units properly linked and reserved"):
        passed_tests += 1
        for unit in units:
            info(f"  Unit {unit.serial_number}: Linked=✓ Reserved=✓ Available={unit.is_available_for_sale}")

print("\n" + "=" * 60)
print("TEST 6: API RESPONSE CHECK")
print("=" * 60)

# Test 6.1: Simulate API response for installation_units
total_tests += 1
if test_service:
    from services.api.serializers import ServiceSerializer
    
    serializer = ServiceSerializer(test_service)
    data = serializer.data
    
    has_units_field = 'installation_units' in data
    if test_result(has_units_field, "API response includes installation_units"):
        passed_tests += 1
        
        if data['installation_units']:
            sample_unit = data['installation_units'][0]
            has_model = 'model' in sample_unit
            has_promo = 'model' in sample_unit and sample_unit['model'] and 'promo_price' in sample_unit['model']
            
            info(f"Sample unit response:")
            info(f"  serial_number: {sample_unit.get('serial_number')}")
            info(f"  model present: {has_model}")
            if has_promo:
                info(f"  promo_price: ₱{sample_unit['model']['promo_price']}")
            
            total_tests += 1
            if test_result(has_promo, "Unit response includes model.promo_price"):
                passed_tests += 1

print("\n" + "=" * 60)
print("TEST 7: BUSINESS LOGIC CHECK")
print("=" * 60)

# Test 7.1: Check if business logic has unit price code
total_tests += 1
import inspect
from services.business_logic import ServiceCompletionHandler

source = inspect.getsource(ServiceCompletionHandler.complete_service)
has_unit_logic = 'installation_units' in source and 'promo_price' in source

if test_result(has_unit_logic, "Service completion includes unit price logic"):
    passed_tests += 1
else:
    warn("Check services/business_logic.py for unit price integration")

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)

percentage = (passed_tests / total_tests * 100) if total_tests > 0 else 0
print(f"\nTotal Tests: {total_tests}")
print(f"Passed: {Colors.PASS}{passed_tests}{Colors.END}")
print(f"Failed: {Colors.FAIL}{total_tests - passed_tests}{Colors.END}")
print(f"Success Rate: {percentage:.1f}%\n")

if percentage == 100:
    print(f"{Colors.PASS}{'=' * 60}")
    print("ALL TESTS PASSED! ✓")
    print(f"{'=' * 60}{Colors.END}\n")
elif percentage >= 80:
    print(f"{Colors.WARN}{'=' * 60}")
    print(f"MOSTLY PASSING ({percentage:.0f}%) - Review failures")
    print(f"{'=' * 60}{Colors.END}\n")
else:
    print(f"{Colors.FAIL}{'=' * 60}")
    print(f"NEEDS ATTENTION ({percentage:.0f}% passing)")
    print(f"{'=' * 60}{Colors.END}\n")

print("\nNext Steps:")
print("1. Review any failed tests above")
print("2. Follow INSTALLATION_UNIT_TESTING_GUIDE.md for manual frontend testing")
print("3. Create test data if prerequisites failed")
print("4. Run recalculation command if revenue tests failed")
print("\nFor detailed testing guide: cat INSTALLATION_UNIT_TESTING_GUIDE.md\n")

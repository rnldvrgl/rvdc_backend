"""
Test data generator for installation service testing.
Creates brands, models, and available units for testing.

Run: python manage.py shell < create_test_data.py
"""

from decimal import Decimal
from django.utils import timezone
from installations.models import AirconBrand, AirconModel, AirconUnit
from inventory.models import Stall
from clients.models import Client

print("=" * 60)
print("CREATING TEST DATA FOR INSTALLATION SERVICES")
print("=" * 60)

# Get main stall
main_stall = Stall.objects.filter(stall_type='main', is_system=True).first()
if not main_stall:
    print("❌ ERROR: Main stall not found. Run: python manage.py setup_stalls")
    exit(1)

print(f"✓ Using stall: {main_stall.name}")

# Create test brands
brands_data = [
    "Carrier",
    "Daikin", 
    "Mitsubishi",
    "LG",
    "Samsung",
]

print("\n📦 Creating Brands...")
brands = {}
for brand_name in brands_data:
    brand, created = AirconBrand.objects.get_or_create(name=brand_name)
    brands[brand_name] = brand
    status = "Created" if created else "Exists"
    print(f"  {status}: {brand_name}")

# Create test models
models_data = [
    {
        'brand': 'Carrier',
        'name': 'Crystal 1.0HP',
        'retail_price': 20000,
        'discount': 10,
        'type': 'split',
        'hp': '1.0',
        'inverter': True,
    },
    {
        'brand': 'Carrier',
        'name': 'Crystal 1.5HP',
        'retail_price': 25000,
        'discount': 10,
        'type': 'split',
        'hp': '1.5',
        'inverter': True,
    },
    {
        'brand': 'Daikin',
        'name': 'Inverter 2.0HP',
        'retail_price': 35000,
        'discount': 15,
        'type': 'split',
        'hp': '2.0',
        'inverter': True,
    },
    {
        'brand': 'Mitsubishi',
        'name': 'Window Type 1.0HP',
        'retail_price': 18000,
        'discount': 5,
        'type': 'window',
        'hp': '1.0',
        'inverter': False,
    },
    {
        'brand': 'LG',
        'name': 'Dual Inverter 1.5HP',
        'retail_price': 30000,
        'discount': 12,
        'type': 'split',
        'hp': '1.5',
        'inverter': True,
    },
]

print("\n🏷️  Creating Models...")
models = []
for model_data in models_data:
    brand = brands[model_data['brand']]
    model, created = AirconModel.objects.get_or_create(
        brand=brand,
        name=model_data['name'],
        defaults={
            'retail_price': Decimal(str(model_data['retail_price'])),
            'discount_percentage': Decimal(str(model_data['discount'])),
            'aircon_type': model_data['type'],
            'horsepower': model_data['hp'],
            'is_inverter': model_data['inverter'],
        }
    )
    models.append(model)
    
    status = "Created" if created else "Exists"
    promo = model.promo_price
    savings = model.retail_price - promo
    
    print(f"  {status}: {brand.name} {model.name}")
    print(f"    Retail: ₱{model.retail_price:,.2f} → Promo: ₱{promo:,.2f} (Save ₱{savings:,.2f})")

# Create test units
print("\n📱 Creating Available Units...")

units_created = 0
units_existed = 0

for model in models:
    # Create 2-3 units per model
    num_units = 2 if model.retail_price < 25000 else 3
    
    for i in range(num_units):
        serial = f"{model.brand.name[:3].upper()}-{model.horsepower.replace('.', '')}-{timezone.now().year}-{i+1:03d}"
        outdoor_serial = f"{serial}-OUT" if model.aircon_type == 'split' else None
        
        unit, created = AirconUnit.objects.get_or_create(
            serial_number=serial,
            defaults={
                'model': model,
                'outdoor_serial_number': outdoor_serial,
                'stall': main_stall,
                'warranty_period_months': 12,
            }
        )
        
        if created:
            units_created += 1
            print(f"  ✓ {serial} ({model.brand.name} {model.name})")
        else:
            units_existed += 1

print(f"\n✓ Units Created: {units_created}")
print(f"✓ Units Already Existed: {units_existed}")

# Create test client if none exists
print("\n👤 Checking Test Client...")
test_client, created = Client.objects.get_or_create(
    full_name="Test Customer",
    defaults={
        'contact_number': '09171234567',
        'address': '123 Test Street, Test City',
    }
)
status = "Created" if created else "Exists"
print(f"  {status}: {test_client.full_name}")

# Summary
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)

total_brands = AirconBrand.objects.count()
total_models = AirconModel.objects.count()
total_units = AirconUnit.objects.count()
available_units = AirconUnit.objects.filter(
    sale__isnull=True,
    reserved_by__isnull=True,
    is_sold=False
).count()

print(f"Total Brands: {total_brands}")
print(f"Total Models: {total_models}")
print(f"Total Units: {total_units}")
print(f"Available for Sale: {available_units}")

print("\n✅ TEST DATA READY!")
print("\nNext Steps:")
print("1. Start frontend: cd rvdc && npm run dev")
print("2. Go to Services → New Service")
print("3. Create Installation service")
print("4. Add units and test!")
print("\nFor testing guide: cat INSTALLATION_UNIT_TESTING_GUIDE.md")
print("For quick checklist: cat FRONTEND_QUICK_TEST.md")
print("For automated tests: python manage.py shell < test_installation_units.py\n")

# Show sample units for quick reference
print("=" * 60)
print("AVAILABLE UNITS FOR TESTING")
print("=" * 60)

sample_units = AirconUnit.objects.filter(
    sale__isnull=True,
    reserved_by__isnull=True,
    is_sold=False
)[:10]
for unit in sample_units:
    print(f"\n{unit.serial_number}")
    if unit.model:
        print(f"  Model: {unit.model.brand.name} {unit.model.name}")
        print(f"  Price: ₱{unit.model.promo_price:,.2f}")
        print(f"  Type: {unit.model.get_aircon_type_display()}")
        print(f"  HP: {unit.model.horsepower}")
        print(f"  Inverter: {'Yes' if unit.model.is_inverter else 'No'}")

if sample_units.count() > 10:
    print(f"\n... and {available_units - 10} more units")

print("\n" + "=" * 60 + "\n")

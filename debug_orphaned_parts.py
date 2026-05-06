"""
Debug script to analyze parts mismatch in a service.

Usage:
    python manage.py shell < debug_orphaned_parts.py
    
Or:
    docker compose exec api python manage.py shell < debug_orphaned_parts.py
"""

from decimal import Decimal
from services.models import Service, ApplianceItemUsed, ServiceItemUsed
from sales.models import SalesItem

# Get the service with MIKE DIZON (adjust ID as needed)
# Let's check all services with in_progress or completed status
services = Service.objects.filter(is_deleted=False).select_related(
    'client',
    'related_sub_transaction',
).prefetch_related(
    'appliances__items_used',
    'service_items',
)

print("\n" + "="*100)
print("SERVICE PARTS ANALYSIS - DEBUGGING ORPHANED PARTS")
print("="*100)

for service in services[:10]:  # Analyze first 10 services
    print(f"\n📋 Service #{service.id} - {service.client} (Status: {service.status})")
    print(f"   Main TX: {service.related_transaction_id}, Sub TX: {service.related_sub_transaction_id}")
    
    # Collect all parts from appliances
    appliance_parts = []
    for appliance in service.appliances.all():
        for item_used in appliance.items_used.all():
            appliance_parts.append({
                'source': f"Appliance: {appliance}",
                'item_id': item_used.item_id,
                'item_name': str(item_used.item) if item_used.item else 'CUSTOM',
                'quantity': item_used.quantity,
                'free_quantity': item_used.free_quantity,
                'is_free': item_used.is_free,
                'price': item_used.discounted_price,
                'custom_price': item_used.custom_price,
            })
    
    # Collect all service-level parts
    service_parts = []
    for item_used in service.service_items.all():
        service_parts.append({
            'source': 'Service Level',
            'item_id': item_used.item_id,
            'item_name': str(item_used.item) if item_used.item else 'CUSTOM',
            'quantity': item_used.quantity,
            'free_quantity': item_used.free_quantity,
            'is_free': item_used.is_free,
            'price': item_used.discounted_price,
            'custom_price': item_used.custom_price,
        })
    
    all_parts = appliance_parts + service_parts
    
    if not all_parts:
        print("   ℹ️  No parts in this service")
        continue
    
    print(f"\n   📦 PARTS ADDED TO SERVICE ({len(all_parts)} total):")
    total_should_be = Decimal('0.00')
    for part in all_parts:
        charged_qty = part['quantity'] - part['free_quantity']
        unit_price = part['price'] or part['custom_price'] or Decimal('0.00')
        line_total = charged_qty * unit_price
        total_should_be += line_total
        
        is_free_indicator = "🆓 FREE" if part['is_free'] else ""
        print(f"      • {part['source']:<30} | {part['item_name']:<30} | "
              f"Qty: {charged_qty:<5} | Price: ₱{unit_price:<8.2f} | Total: ₱{line_total:<8.2f} {is_free_indicator}")
    
    print(f"   ✓ Total parts value SHOULD BE: ₱{total_should_be:.2f}")
    
    # Check sales transaction
    if not service.related_sub_transaction:
        print(f"\n   ❌ NO SUB SALES TRANSACTION - ALL ₱{total_should_be:.2f} IS MISSING!")
    else:
        sub_tx = service.related_sub_transaction
        sub_items = sub_tx.items.all()
        
        print(f"\n   🧾 SALES TRANSACTION (Sub) #{sub_tx.id} has ({len(sub_items)} items):")
        sales_parts_total = Decimal('0.00')
        for sales_item in sub_items:
            line_total = sales_item.quantity * (sales_item.final_price_per_unit or Decimal('0.00'))
            sales_parts_total += line_total
            item_desc = f"{sales_item.item.name}" if sales_item.item else sales_item.description
            print(f"      • {item_desc:<30} | Qty: {sales_item.quantity:<5} | "
                  f"Price: ₱{sales_item.final_price_per_unit:<8.2f} | Total: ₱{line_total:<8.2f}")
        
        print(f"   ✓ Total in sales transaction: ₱{sales_parts_total:.2f}")
        
        if total_should_be > sales_parts_total:
            missing = total_should_be - sales_parts_total
            print(f"\n   ⚠️  MISSING: ₱{missing:.2f} ({((missing/total_should_be)*100):.1f}%)")
        elif total_should_be == sales_parts_total:
            print(f"\n   ✅ COMPLETE - All parts are in the sales transaction")
        else:
            overage = sales_parts_total - total_should_be
            print(f"\n   ⚠️  OVERAGE: ₱{overage:.2f} (More in sales than parts added)")

print("\n" + "="*100)
print("END OF ANALYSIS")
print("="*100 + "\n")

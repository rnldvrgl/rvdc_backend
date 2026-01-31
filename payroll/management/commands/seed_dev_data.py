from datetime import date, datetime, timedelta
from datetime import time as dt_time
from decimal import Decimal
from typing import List

from clients.models import Client
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.timezone import get_current_timezone, make_aware
from inventory.models import (
    Item,
    ProductCategory,
    Stall,
    Stock,
    StockRoomStock,
)
from payroll.models import AdditionalEarning, TimeEntry, WeeklyPayroll
from sales.models import SalesTransaction


class Command(BaseCommand):
    help = (
        "Seed initial items, stockroom, Sub stall stock, and 1-week attendance for testing development. "
        "Also seeds payroll additional earnings and deductions, plus sample sales and expenses."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--employee-username",
            type=str,
            default="tech1",
            help="Username of the employee to seed attendance for (will be created if not exists).",
        )
        parser.add_argument(
            "--hourly-rate",
            type=str,
            default="100.00",
            help="Hourly rate for seeded weekly payroll (as decimal string).",
        )
        parser.add_argument(
            "--week-start",
            type=str,
            default="auto",
            help="Week start date (YYYY-MM-DD). If 'auto', uses most recent Monday.",
        )
        parser.add_argument(
            "--scale",
            type=int,
            default=1,
            help="Scale factor for dataset size (duplicates sales/expenses/remittances across subsequent days).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        employee_username = options.get("employee_username", "tech1")
        hourly_rate = Decimal(options.get("hourly_rate", "100.00"))
        scale = int(options.get("scale", 1))

        # Determine the target week start date
        week_start_opt = options.get("week_start", "auto")
        if week_start_opt == "auto":
            week_start = self._get_last_monday(date.today())
        else:
            try:
                y, m, d = [int(x) for x in week_start_opt.split("-")]
                week_start = date(y, m, d)
            except Exception:
                self.stdout.write(self.style.ERROR("Invalid --week-start format, using auto."))
                week_start = self._get_last_monday(date.today())

        self.stdout.write(self.style.WARNING(f"Starting development seed for week: {week_start}..."))

        # 1) Ensure Sub stall exists
        sub_stall = self._ensure_sub_stall()

        # 2) Seed basic product categories and items
        items = self._seed_items()

        # 3) Ensure StockRoomStock records exist
        self._seed_stockroom_quantities(items)

        # 4) Ensure Stock rows exist for Sub stall
        self._ensure_sub_stall_stock(items, sub_stall)

        # 5) Ensure a test client exists with required location fields
        client = self._ensure_client("Development Client")

        # 6) Ensure an employee exists with required fields
        employee = self._ensure_employee(employee_username)

        # 7) Seed 1-week attendance
        created_entries = self._seed_week_attendance(employee, week_start)
        self.stdout.write(self.style.SUCCESS(f"✅ Created {created_entries} time entries"))

        # 8) Create WeeklyPayroll
        payroll = self._seed_weekly_payroll(employee, week_start, hourly_rate)

        # 9) Seed additional earnings
        add_earn_count = self._seed_additional_earnings(employee, week_start)
        self.stdout.write(self.style.SUCCESS(f"✅ Created {add_earn_count} additional earnings"))

        # 10) Apply sample deductions (FIXED for JSON serialization)
        self._apply_payroll_deductions(payroll)

        # 11) Generate sample sales and expenses
        sales_count, expenses_count = self._generate_sales_and_expenses(
            sub_stall=sub_stall,
            employee=employee,
            client=client,
            items=items,
            week_start=week_start,
            scale=scale,
        )
        self.stdout.write(self.style.SUCCESS(f"✅ Generated {sales_count} sales, {expenses_count} expenses"))

        # 12) Final Recompute
        payroll.compute_from_daily_attendance(include_unapproved=False)
        payroll.save()

        # Seed receivables and remittances
        linked_sale = SalesTransaction.objects.filter(stall=sub_stall).order_by("id").first()
        cheques_created = self._seed_receivables_cheques(client, employee, week_start, linked_sale)
        remittances_created = self._seed_remittances_records(sub_stall, employee, week_start, scale)
        self.stdout.write(self.style.SUCCESS(f"✅ Created {cheques_created} cheques, {remittances_created} remittances"))

        self.stdout.write(self.style.SUCCESS(f"\n🎉 Seed complete! Payroll Net Pay: ₱{payroll.net_pay:,.2f}"))

    # ---------- Core Helpers ----------

    def _apply_payroll_deductions(self, payroll: WeeklyPayroll):
        """
        Applies sample deductions.
        FIX: Converts Decimal to float to allow JSON serialization.
        """
        deductions = {
            "SSS": float(Decimal("150.00")),
            "PhilHealth": float(Decimal("50.00")),
            "Pag-IBIG": float(Decimal("100.00")),
        }
        payroll.deductions = deductions
        payroll.save(update_fields=["deductions"])
        self.stdout.write(self.style.SUCCESS("✅ Applied JSON-safe deductions"))

    def _localize(self, d: date, t: dt_time) -> datetime:
        dt = datetime.combine(d, t)
        return make_aware(dt, timezone=get_current_timezone())

    def _get_last_monday(self, today: date) -> date:
        weekday = today.weekday()
        return today - timedelta(days=weekday)

    def _ensure_sub_stall(self) -> Stall:
        sub_stall, created = Stall.all_objects.get_or_create(
            name="Sub",
            location="Parts",
            defaults={"inventory_enabled": True, "is_system": True, "is_deleted": False},
        )
        if created:
            self.stdout.write(self.style.SUCCESS("✅ Created Sub (Parts) stall"))
        return sub_stall

    def _seed_items(self) -> List[Item]:
        cat_parts, _ = ProductCategory.all_objects.get_or_create(name="Parts")
        seed_defs = [
            ("Copper Tube 1/4\"", cat_parts, "ft", Decimal("150.00")),
            ("Copper Tube 1/2\"", cat_parts, "ft", Decimal("220.00"))
        ]
        items = []
        for name, cat, unit, price in seed_defs:
            item, _ = Item.all_objects.get_or_create(
                name=name,
                defaults={
                    "category": cat,
                    "unit_of_measure": unit,
                    "retail_price": price
                }
            )
            items.append(item)
            self.stdout.write(self.style.SUCCESS(f"✅ Item: {name}"))
        return items

    def _seed_stockroom_quantities(self, items):
        for item in items:
            StockRoomStock.objects.get_or_create(item=item, defaults={"quantity": 100})
            self.stdout.write(self.style.SUCCESS(f"✅ StockRoom for {item.name}"))

    def _ensure_sub_stall_stock(self, items, sub_stall):
        for item in items:
            Stock.objects.get_or_create(item=item, stall=sub_stall, defaults={"quantity": 0})

    def _ensure_client(self, full_name):
        """
        Create or get a client with required location fields.
        """
        client, created = Client.objects.get_or_create(
            full_name=full_name,
            defaults={
                "contact_number": "09123456789",
                "province": "Pampanga",
                "city": "Mabalacat City",
                "barangay": "Dau",
                "address": "123 Sample Street",
                "is_deleted": False,
                "is_blocklisted": False,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"✅ Created client: {full_name}"))
        return client

    def _ensure_employee(self, username):
        """
        Create or get an employee with required fields including basic_salary.
        """
        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "role": "technician",
                "first_name": "Test",
                "last_name": "Employee",
                "email": f"{username}@example.com",
                "contact_number": "09987654321",
                "basic_salary": Decimal("15000.00"),  # Added required field
                "is_deleted": False,
            }
        )
        if created:
            user.set_password("devpassword123")
            user.save()
            self.stdout.write(self.style.SUCCESS(f"✅ Created employee: {username}"))
        return user

    def _seed_week_attendance(self, employee, week_start):
        created = 0
        for i in range(5):
            day = week_start + timedelta(days=i)
            TimeEntry.objects.get_or_create(
                employee=employee,
                clock_in=self._localize(day, dt_time(9, 0)),
                defaults={
                    "clock_out": self._localize(day, dt_time(18, 0)),
                    "unpaid_break_minutes": 60,
                    "approved": True,
                }
            )
            created += 1
            self.stdout.write(self.style.SUCCESS(f"✅ Entry for {day}"))
        return created

    def _seed_weekly_payroll(self, employee, week_start, hourly_rate):
        payroll, created = WeeklyPayroll.objects.get_or_create(
            employee=employee,
            week_start=week_start,
            defaults={
                "hourly_rate": hourly_rate,
                "status": "draft"
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS("✅ Created weekly payroll"))
        return payroll

    def _seed_additional_earnings(self, employee, week_start):
        earnings = [
            ("overtime", Decimal("500.00"), 2),
            ("installation_pct", Decimal("1000.00"), 4)
        ]
        for category, amount, offset in earnings:
            AdditionalEarning.objects.get_or_create(
                employee=employee,
                earning_date=week_start + timedelta(days=offset),
                category=category,
                defaults={"amount": amount}
            )
        return len(earnings)

    def _seed_receivables_cheques(self, client, employee, week_start, sales_txn):
        from receivables.models import ChequeCollection
        tue = self._localize(week_start + timedelta(days=1), dt_time(11, 0))
        ChequeCollection.objects.get_or_create(
            cheque_number="DEV-CHK-001",
            defaults={
                "client": client,
                "date_collected": tue,
                "cheque_date": tue.date(),
                "billing_amount": Decimal("1000.00"),
                "cheque_amount": Decimal("1000.00"),
                "bank_name": "BDO",
                "status": "pending"
            }
        )
        return 1

    def _seed_remittances_records(self, sub_stall, employee, week_start, scale):
        from remittances.models import RemittanceRecord
        day = self._localize(week_start, dt_time(22, 0))
        RemittanceRecord.objects.get_or_create(
            stall=sub_stall,
            created_at=day,
            defaults={
                "total_sales_cash": Decimal("5000.00"),
                "remitted_by": employee
            }
        )
        return 1

    def _generate_sales_and_expenses(self, **kwargs):
        # Placeholder for brevity, you can keep your existing logic here
        return 0, 0

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Hard-delete all sales and stock ledgers (keeps master data such as Items, Stalls, Users)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            type=str,
            help='Safety confirmation token. Use --confirm "HARD-DELETE-ACK" to proceed.',
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Preview counts without deleting."
        )

    def handle(self, *args, **options):
        confirm = options.get("confirm")
        dry_run = bool(options.get("dry_run") or False)

        # Import models lazily to avoid app loading issues during command import
        # Some apps may not exist in every deployment; guard imports accordingly.
        sales_models = {}
        inventory_models = {}
        expenses_models = {}

        # Sales models
        try:
            from sales.models import SalesItem, SalesTransaction

            sales_models["SalesTransaction"] = SalesTransaction
            sales_models["SalesItem"] = SalesItem
        except Exception:
            pass

        # Inventory models
        try:
            from inventory.models import (
                Stock,
                StockRoomStock,
                StockTransfer,
                StockTransferItem,
            )

            inventory_models["Stock"] = Stock
            inventory_models["StockRoomStock"] = StockRoomStock
            inventory_models["StockTransfer"] = StockTransfer
            inventory_models["StockTransferItem"] = StockTransferItem
        except Exception:
            pass

        # Expenses models (only transfer-related entries are targeted)
        try:
            from expenses.models import Expense, ExpenseItem

            expenses_models["Expense"] = Expense
            expenses_models["ExpenseItem"] = ExpenseItem
        except Exception:
            pass

        # Build counts for preview/reporting
        counts = {}

        # Sales counts
        if "SalesItem" in sales_models:
            counts["SalesItem"] = sales_models["SalesItem"].objects.count()
        if "SalesTransaction" in sales_models:
            counts["SalesTransaction"] = sales_models[
                "SalesTransaction"
            ].objects.count()

        # Inventory counts
        if "StockTransferItem" in inventory_models:
            counts["StockTransferItem"] = inventory_models[
                "StockTransferItem"
            ].objects.count()
        if "StockTransfer" in inventory_models:
            counts["StockTransfer"] = inventory_models["StockTransfer"].objects.count()
        if "Stock" in inventory_models:
            counts["Stock"] = inventory_models["Stock"].objects.count()
        if "StockRoomStock" in inventory_models:
            counts["StockRoomStock"] = inventory_models[
                "StockRoomStock"
            ].objects.count()

        # Expenses (transfer-only) counts
        if "ExpenseItem" in expenses_models and "Expense" in expenses_models:
            counts["ExpenseItem(transfer)"] = (
                expenses_models["ExpenseItem"]
                .objects.filter(expense__source="transfer")
                .count()
            )
            counts["Expense(transfer)"] = (
                expenses_models["Expense"].objects.filter(source="transfer").count()
            )

        # Dry-run: print counts and exit
        if dry_run:
            self.stdout.write(
                self.style.WARNING("Dry-run mode: no deletions performed.")
            )
            for label, value in counts.items():
                self.stdout.write(f"{label}: {value}")
            return

        # Require explicit confirmation token for destructive action
        if confirm != "HARD-DELETE-ACK":
            raise CommandError(
                'Confirmation required. Use --confirm "HARD-DELETE-ACK" to proceed.'
            )

        # Execute deletions in a dependency-safe order
        with transaction.atomic():
            # Expenses (transfer-only) — delete items before expenses
            if "ExpenseItem" in expenses_models:
                expenses_models["ExpenseItem"].objects.filter(
                    expense__source="transfer"
                ).delete()
            if "Expense" in expenses_models:
                expenses_models["Expense"].objects.filter(source="transfer").delete()

            # Sales — delete items before transactions
            if "SalesItem" in sales_models:
                sales_models["SalesItem"].objects.all().delete()
            if "SalesTransaction" in sales_models:
                sales_models["SalesTransaction"].objects.all().delete()

            # Inventory — delete transfer items before transfers
            if "StockTransferItem" in inventory_models:
                inventory_models["StockTransferItem"].objects.all().delete()
            if "StockTransfer" in inventory_models:
                inventory_models["StockTransfer"].objects.all().delete()

            # Inventory stock
            if "Stock" in inventory_models:
                inventory_models["Stock"].objects.all().delete()
            if "StockRoomStock" in inventory_models:
                inventory_models["StockRoomStock"].objects.all().delete()

        # Final report
        self.stdout.write(self.style.SUCCESS("Ledger wipe completed successfully."))
        for label, value in counts.items():
            self.stdout.write(f"Deleted {label}: {value}")

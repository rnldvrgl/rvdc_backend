import json
import logging
import importlib
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from sales.models import SalesTransaction

logger = logging.getLogger(__name__)


def _get_google_sync_config() -> dict:
    config = {
        "enabled": bool(getattr(settings, "GOOGLE_SHEETS_SYNC_ENABLED", False)),
        "spreadsheet_id": getattr(settings, "GOOGLE_SHEETS_SPREADSHEET_ID", "").strip(),
        "worksheet_name": getattr(settings, "GOOGLE_SHEETS_WORKSHEET_NAME", "Sub Stall Sales"),
        "sub_stall_type": getattr(settings, "GOOGLE_SHEETS_SUB_STALL_TYPE", "sub"),
        "service_account_json": getattr(settings, "GOOGLE_SERVICE_ACCOUNT_JSON", ""),
        "service_account_file": getattr(settings, "GOOGLE_SERVICE_ACCOUNT_FILE", ""),
    }

    try:
        from users.models import SystemSettings

        system_settings = SystemSettings.get_settings()
        config["enabled"] = bool(system_settings.google_sheets_sync_enabled)
        config["spreadsheet_id"] = (system_settings.google_sheets_spreadsheet_id or "").strip()
        config["worksheet_name"] = (
            system_settings.google_sheets_worksheet_name or config["worksheet_name"]
        )
        config["sub_stall_type"] = (
            system_settings.google_sheets_sub_stall_type or config["sub_stall_type"]
        )
        if (system_settings.google_service_account_json or "").strip():
            config["service_account_json"] = system_settings.google_service_account_json
    except Exception as exc:
        logger.warning("Using environment Google Sheets config fallback: %s", exc)

    return config


def _get_service_account_credentials(sync_config: dict):
    service_account_module = importlib.import_module("google.oauth2.service_account")
    Credentials = service_account_module.Credentials

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]

    raw_json = sync_config.get("service_account_json", "")
    if raw_json:
        try:
            info = json.loads(raw_json)
            return Credentials.from_service_account_info(info, scopes=scopes)
        except Exception as exc:
            logger.error("Invalid service account JSON in system settings: %s", exc)
            return None

    json_path = sync_config.get("service_account_file", "")
    if json_path:
        try:
            return Credentials.from_service_account_file(json_path, scopes=scopes)
        except Exception as exc:
            logger.error("Unable to read GOOGLE_SERVICE_ACCOUNT_FILE=%s: %s", json_path, exc)
            return None

    logger.warning("Google Sheets sync skipped: no service-account credentials configured")
    return None


def _serialize_decimal(value):
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return str(value)


def _summarize_items(transaction: SalesTransaction) -> str:
    parts = []
    for line in transaction.items.all():
        label = line.description or (line.item.name if line.item else "Item")
        unit_price = _serialize_decimal(line.final_price_per_unit)
        parts.append(f"{line.quantity} x {label} @ {unit_price}")
    return " | ".join(parts)


def _summarize_payments(transaction: SalesTransaction) -> str:
    parts = []
    for payment in transaction.payments.all().order_by("payment_date"):
        paid_at = timezone.localtime(payment.payment_date).strftime("%Y-%m-%d %H:%M:%S")
        parts.append(f"{payment.payment_type}:{_serialize_decimal(payment.amount)} ({paid_at})")
    return " | ".join(parts)


def _build_row(transaction: SalesTransaction):
    effective_date = transaction.transaction_date or timezone.localdate(transaction.created_at)
    created_local = timezone.localtime(transaction.created_at).strftime("%Y-%m-%d %H:%M:%S")
    updated_local = timezone.localtime(transaction.updated_at).strftime("%Y-%m-%d %H:%M:%S")
    client_name = transaction.client.full_name if transaction.client else ""
    clerk_name = ""
    if transaction.sales_clerk:
        clerk_name = transaction.sales_clerk.get_full_name() or transaction.sales_clerk.username

    return [
        str(transaction.id),
        str(transaction.system_receipt_number),
        transaction.receipt_book or "",
        transaction.manual_receipt_number or "",
        transaction.document_type,
        transaction.transaction_type,
        str(effective_date),
        created_local,
        updated_local,
        transaction.stall.name if transaction.stall else "",
        transaction.stall.stall_type if transaction.stall else "",
        client_name,
        clerk_name,
        transaction.payment_status,
        _serialize_decimal(transaction.total_items),
        _serialize_decimal(transaction.subtotal),
        _serialize_decimal(transaction.order_discount),
        _serialize_decimal(transaction.computed_total),
        _serialize_decimal(transaction.total_paid),
        _serialize_decimal(transaction.change_amount),
        "TRUE" if transaction.voided else "FALSE",
        "TRUE" if transaction.is_deleted else "FALSE",
        _summarize_items(transaction),
        _summarize_payments(transaction),
    ]


def _headers():
    return [
        "transaction_id",
        "system_receipt_number",
        "receipt_book",
        "manual_receipt_number",
        "document_type",
        "transaction_type",
        "transaction_date",
        "created_at",
        "updated_at",
        "stall_name",
        "stall_type",
        "client_name",
        "sales_clerk",
        "payment_status",
        "total_items",
        "subtotal",
        "order_discount",
        "computed_total",
        "total_paid",
        "change_amount",
        "voided",
        "is_deleted",
        "items_summary",
        "payments_summary",
    ]


def sync_sales_transaction_to_google_sheet(transaction_id: int) -> bool:
    sync_config = _get_google_sync_config()

    if not sync_config["enabled"]:
        return False

    spreadsheet_id = sync_config["spreadsheet_id"]
    if not spreadsheet_id:
        logger.warning("Google Sheets sync skipped: spreadsheet ID is missing")
        return False

    sub_stall_type = sync_config["sub_stall_type"]

    try:
        transaction = (
            SalesTransaction.objects.select_related("stall", "client", "sales_clerk")
            .prefetch_related("items__item", "payments")
            .get(pk=transaction_id)
        )
    except SalesTransaction.DoesNotExist:
        logger.warning("Google Sheets sync skipped: SalesTransaction %s does not exist", transaction_id)
        return False

    if not transaction.stall or transaction.stall.stall_type != sub_stall_type:
        return False

    credentials = _get_service_account_credentials(sync_config)
    if credentials is None:
        return False

    worksheet_name = sync_config["worksheet_name"]

    try:
        discovery_module = importlib.import_module("googleapiclient.discovery")
        build = discovery_module.build

        service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        sheet_api = service.spreadsheets().values()

        # Ensure headers exist for readability and stable upsert layout.
        header_range = f"{worksheet_name}!1:1"
        header_resp = sheet_api.get(spreadsheetId=spreadsheet_id, range=header_range).execute()
        if not header_resp.get("values"):
            sheet_api.update(
                spreadsheetId=spreadsheet_id,
                range=f"{worksheet_name}!A1:X1",
                valueInputOption="RAW",
                body={"values": [_headers()]},
            ).execute()

        id_column = sheet_api.get(
            spreadsheetId=spreadsheet_id,
            range=f"{worksheet_name}!A2:A",
        ).execute().get("values", [])

        target_row = None
        for idx, row in enumerate(id_column, start=2):
            if row and row[0] == str(transaction.id):
                target_row = idx
                break

        row_values = _build_row(transaction)
        if target_row:
            sheet_api.update(
                spreadsheetId=spreadsheet_id,
                range=f"{worksheet_name}!A{target_row}:X{target_row}",
                valueInputOption="USER_ENTERED",
                body={"values": [row_values]},
            ).execute()
        else:
            sheet_api.append(
                spreadsheetId=spreadsheet_id,
                range=f"{worksheet_name}!A:X",
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": [row_values]},
            ).execute()

        return True
    except Exception as exc:
        logger.exception("Google Sheets sync failed for transaction %s: %s", transaction_id, exc)
        return False

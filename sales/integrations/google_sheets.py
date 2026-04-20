import importlib
import json
import logging
from datetime import date
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db.models import Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from expenses.models import Expense
from inventory.models import Stall
from remittances.models import RemittanceRecord
from sales.models import SalesTransaction

logger = logging.getLogger(__name__)


def _get_google_sync_config() -> dict:
    config = {
        "enabled": bool(getattr(settings, "GOOGLE_SHEETS_SYNC_ENABLED", False)),
        "sub_spreadsheet_id": getattr(settings, "GOOGLE_SHEETS_SPREADSHEET_ID", "").strip(),
        "main_spreadsheet_id": getattr(settings, "GOOGLE_SHEETS_MAIN_SPREADSHEET_ID", "").strip(),
        "sync_scope": getattr(settings, "GOOGLE_SHEETS_SUB_STALL_TYPE", "sub"),
        "service_account_json": getattr(settings, "GOOGLE_SERVICE_ACCOUNT_JSON", ""),
        "service_account_file": getattr(settings, "GOOGLE_SERVICE_ACCOUNT_FILE", ""),
    }

    try:
        from users.models import SystemSettings

        system_settings = SystemSettings.get_settings()
        config["enabled"] = bool(system_settings.google_sheets_sync_enabled)
        config["sub_spreadsheet_id"] = (system_settings.google_sheets_spreadsheet_id or "").strip()
        config["main_spreadsheet_id"] = (
            getattr(system_settings, "google_sheets_main_spreadsheet_id", "") or ""
        ).strip()
        config["sync_scope"] = (system_settings.google_sheets_sub_stall_type or "sub").strip().lower()
        if (system_settings.google_service_account_json or "").strip():
            config["service_account_json"] = system_settings.google_service_account_json
    except Exception as exc:
        logger.warning("Using environment Google Sheets config fallback: %s", exc)

    # Backward compatibility: if main is empty, fallback to sub sheet.
    if not config["main_spreadsheet_id"]:
        config["main_spreadsheet_id"] = config["sub_spreadsheet_id"]

    if config["sync_scope"] not in {"sub", "main", "both"}:
        config["sync_scope"] = "sub"

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


def _spreadsheet_id_for_stall(sync_config: dict, stall_type: str) -> str:
    if stall_type == "main":
        return (sync_config.get("main_spreadsheet_id") or "").strip()
    return (sync_config.get("sub_spreadsheet_id") or "").strip()


def _get_sheets_clients(sync_config: dict, spreadsheet_id: str):
    if not spreadsheet_id:
        return None, None, "Spreadsheet ID is missing"

    credentials = _get_service_account_credentials(sync_config)
    if credentials is None:
        return None, None, "Service account credentials are not configured or invalid"

    try:
        discovery_module = importlib.import_module("googleapiclient.discovery")
        build = discovery_module.build
        service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        return service, service.spreadsheets().values(), ""
    except Exception as exc:
        logger.exception("Failed to initialize Google Sheets API client: %s", exc)
        return None, None, str(exc)


def _scope_stall_types(sync_scope: str) -> list[str]:
    if sync_scope == "both":
        return ["sub", "main"]
    if sync_scope == "main":
        return ["main"]
    return ["sub"]


def _a1_range(worksheet_name: str, a1_notation: str) -> str:
    escaped = (worksheet_name or "").replace("'", "''")
    return f"'{escaped}'!{a1_notation}"


def _daily_tab_name(target_date: date) -> str:
    return target_date.strftime("%B %d").upper()


def _effective_date(transaction: SalesTransaction) -> date:
    if transaction.transaction_date:
        return transaction.transaction_date
    return timezone.localtime(transaction.created_at).date()


def _serialize_decimal(value) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return str(value)


def _payment_method_label(transaction: SalesTransaction) -> str:
    methods = []
    for payment in transaction.payments.all().order_by("payment_date"):
        method = (payment.payment_type or "").upper()
        if method and method not in methods:
            methods.append(method)
    return ", ".join(methods)


def _normalize_line_description(line) -> str:
    line_desc = (line.description or "").strip()
    if line_desc and line_desc.lower() != "custom item":
        return line_desc

    if line.item:
        item_name = (line.item.name or "").strip()
        if item_name and item_name.lower() != "custom item":
            return item_name
        item_desc = (line.item.description or "").strip()
        if item_desc:
            return item_desc

    return line_desc


def _build_sales_rows(transactions) -> list[list[str]]:
    rows: list[list[str]] = []

    for transaction in transactions:
        client_name = transaction.client.full_name if transaction.client else ""
        receipt_number = transaction.manual_receipt_number or ""
        book_number = transaction.receipt_book or ""
        payment_method = _payment_method_label(transaction)

        line_rows = []
        for line in transaction.items.all():
            description = _normalize_line_description(line)
            quantity = _serialize_decimal(line.quantity)
            amount = _serialize_decimal(line.line_total)
            line_rows.append([
                quantity,
                description,
                amount,
                client_name,
                book_number,
                receipt_number,
                payment_method,
            ])

        if not line_rows:
            line_rows.append([
                "",
                transaction.note or "",
                _serialize_decimal(transaction.computed_total),
                client_name,
                book_number,
                receipt_number,
                payment_method,
            ])

        rows.extend(line_rows)

    return rows


def _get_expense_rows(stall: Stall, target_date: date) -> list[list[str]]:
    expenses = (
        Expense.objects.filter(stall=stall, expense_date=target_date, is_deleted=False)
        .order_by("id")
    )

    rows: list[list[str]] = []
    for expense in expenses:
        source = "reimbursement" if expense.is_reimbursement else "expense"
        label = (expense.description or expense.vendor or "").strip()
        amount = expense.paid_amount or Decimal("0")
        if expense.is_reimbursement:
            amount = -amount
        rows.append([source, label, _serialize_decimal(amount)])

    return rows


def _get_day_metrics(stall: Stall, target_date: date) -> dict[str, Any]:
    remittance = (
        RemittanceRecord.objects.select_related("cash_breakdown")
        .filter(stall=stall, remittance_date=target_date)
        .first()
    )

    metrics = {
        "total_cash_sales": Decimal("0"),
        "total_gcash_sales": Decimal("0"),
        "total_credit_sales": Decimal("0"),
        "total_debit_sales": Decimal("0"),
        "total_cheque_sales": Decimal("0"),
        "total_expenses": Decimal("0"),
        "cod_for_today": Decimal("0"),
        "expected_remittance": Decimal("0"),
        "remitted_amount": Decimal("0"),
        "declared_amount": Decimal("0"),
        "balance": Decimal("0"),
        "denominations": [],
    }

    cod_info = RemittanceRecord.get_cod_for_date(stall, target_date)
    metrics["cod_for_today"] = Decimal(str(cod_info.get("cod_amount", 0) or 0))

    expense_total = (
        Expense.objects.filter(stall=stall, expense_date=target_date, is_deleted=False)
        .aggregate(total=Coalesce(Sum("paid_amount"), Decimal("0")))
        .get("total")
        or Decimal("0")
    )
    metrics["total_expenses"] = expense_total

    if remittance:
        metrics["total_cash_sales"] = remittance.total_sales_cash or Decimal("0")
        metrics["total_gcash_sales"] = remittance.total_sales_gcash or Decimal("0")
        metrics["total_credit_sales"] = remittance.total_sales_credit or Decimal("0")
        metrics["total_debit_sales"] = remittance.total_sales_debit or Decimal("0")
        metrics["total_cheque_sales"] = remittance.total_sales_cheque or Decimal("0")
        metrics["total_expenses"] = remittance.total_expenses or Decimal("0")
        metrics["expected_remittance"] = remittance.expected_remittance or Decimal("0")
        metrics["remitted_amount"] = Decimal(str(remittance.remitted_amount or 0))
        metrics["declared_amount"] = Decimal(str(remittance.declared_amount or 0))
        metrics["balance"] = remittance.balance or Decimal("0")

        if hasattr(remittance, "cash_breakdown"):
            b = remittance.cash_breakdown
            denoms = [1000, 500, 200, 100, 50, 20, 10, 5, 1]
            for d in denoms:
                remitted_count = int(getattr(b, f"count_{d}", 0) or 0)
                declared_count = int(getattr(b, f"declared_count_{d}", 0) or 0)
                cod_count = max(0, declared_count - remitted_count)
                metrics["denominations"].append([
                    str(d),
                    str(remitted_count),
                    str(declared_count),
                    str(cod_count),
                ])

    return metrics


def _write_block(sheet_api, spreadsheet_id: str, tab_name: str, a1: str, values):
    sheet_api.update(
        spreadsheetId=spreadsheet_id,
        range=_a1_range(tab_name, a1),
        valueInputOption="USER_ENTERED",
        body={"values": values},
    ).execute()


def _ensure_tab(service, spreadsheet_id: str, tab_name: str):
    metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    existing_titles = {
        sheet.get("properties", {}).get("title")
        for sheet in metadata.get("sheets", [])
    }

    if tab_name not in existing_titles:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
        ).execute()


def _clear_day_tab(sheet_api, spreadsheet_id: str, tab_name: str):
    sheet_api.clear(
        spreadsheetId=spreadsheet_id,
        range=_a1_range(tab_name, "A1:Z200"),
        body={},
    ).execute()


def _style_day_tab(service, spreadsheet_id: str, tab_name: str, sales_rows_count: int):
    metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheet_id = None
    for sheet in metadata.get("sheets", []):
        props = sheet.get("properties", {})
        if props.get("title") == tab_name:
            sheet_id = props.get("sheetId")
            break

    if sheet_id is None:
        return

    sales_end_row = max(4, 4 + sales_rows_count)
    requests = [
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 12,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.10, "green": 0.16, "blue": 0.24},
                        "horizontalAlignment": "CENTER",
                        "textFormat": {
                            "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                            "fontSize": 14,
                            "bold": True,
                        },
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 3,
                    "endRowIndex": 4,
                    "startColumnIndex": 0,
                    "endColumnIndex": 7,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.89, "green": 0.93, "blue": 0.98},
                        "textFormat": {"bold": True},
                        "horizontalAlignment": "CENTER",
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
            }
        },
        {
            "setBasicFilter": {
                "filter": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 3,
                        "endRowIndex": sales_end_row,
                        "startColumnIndex": 0,
                        "endColumnIndex": 7,
                    }
                }
            }
        },
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {"frozenRowCount": 4},
                },
                "fields": "gridProperties.frozenRowCount",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 15,
                    "endRowIndex": 16,
                    "startColumnIndex": 8,
                    "endColumnIndex": 11,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.93, "green": 0.95, "blue": 0.98},
                        "textFormat": {"bold": True},
                        "horizontalAlignment": "CENTER",
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
            }
        },
    ]

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": requests},
    ).execute()


def _render_day_tab(service, sheet_api, spreadsheet_id: str, stall: Stall, target_date: date):
    tab_name = _daily_tab_name(target_date)
    _ensure_tab(service, spreadsheet_id, tab_name)
    _clear_day_tab(sheet_api, spreadsheet_id, tab_name)

    transactions = (
        SalesTransaction.objects.select_related("client", "stall")
        .prefetch_related("items__item", "payments")
        .filter(
            stall=stall,
            voided=False,
            is_deleted=False,
        )
        .annotate(effective_date=Coalesce("transaction_date", TruncDate("created_at")))
        .filter(effective_date=target_date)
        .order_by("manual_receipt_number", "id")
    )

    sales_rows = _build_sales_rows(transactions)
    expense_rows = _get_expense_rows(stall, target_date)
    metrics = _get_day_metrics(stall, target_date)

    title = f"{stall.name.upper()} SALES"
    subtitle = target_date.strftime("%A, %B %d, %Y")

    _write_block(sheet_api, spreadsheet_id, tab_name, "A1:G1", [[title]])
    _write_block(sheet_api, spreadsheet_id, tab_name, "A2:G2", [[subtitle]])
    _write_block(
        sheet_api,
        spreadsheet_id,
        tab_name,
        "A4:G4",
        [["Quantity", "Description", "Amount", "Client Name", "Book #", "Receipt #", "Payment Method"]],
    )

    if sales_rows:
        _write_block(
            sheet_api,
            spreadsheet_id,
            tab_name,
            f"A5:G{4 + len(sales_rows)}",
            sales_rows,
        )

    _write_block(sheet_api, spreadsheet_id, tab_name, "I1:J1", [["REMITTANCE SUMMARY", ""]])
    _write_block(
        sheet_api,
        spreadsheet_id,
        tab_name,
        "I2:J11",
        [
            ["Total Cash Sales", _serialize_decimal(metrics["total_cash_sales"])],
            ["Total GCash Sales", _serialize_decimal(metrics["total_gcash_sales"])],
            ["Total Credit Sales", _serialize_decimal(metrics["total_credit_sales"])],
            ["Total Debit Sales", _serialize_decimal(metrics["total_debit_sales"])],
            ["Total Cheque Sales", _serialize_decimal(metrics["total_cheque_sales"])],
            ["Total Expenses", _serialize_decimal(metrics["total_expenses"])],
            ["COD (Prev Day)", _serialize_decimal(metrics["cod_for_today"])],
            ["Expected Remittance", _serialize_decimal(metrics["expected_remittance"])],
            ["Remitted Amount", _serialize_decimal(metrics["remitted_amount"])],
            ["Declared Amount", _serialize_decimal(metrics["declared_amount"])],
        ],
    )

    _write_block(
        sheet_api,
        spreadsheet_id,
        tab_name,
        "I12:J12",
        [["Over / Short", _serialize_decimal(metrics["balance"]) ]],
    )

    _write_block(sheet_api, spreadsheet_id, tab_name, "I15:K15", [["EXPENSES / GCASH", "", ""]])
    _write_block(sheet_api, spreadsheet_id, tab_name, "I16:K16", [["Type", "Description", "Amount"]])
    if expense_rows:
        _write_block(
            sheet_api,
            spreadsheet_id,
            tab_name,
            f"I17:K{16 + len(expense_rows)}",
            expense_rows,
        )

    _write_block(sheet_api, spreadsheet_id, tab_name, "A14:D14", [["CASH / COINS BREAKDOWN", "", "", ""]])
    _write_block(sheet_api, spreadsheet_id, tab_name, "A15:D15", [["Denomination", "Remitted", "Declared", "COD"]])
    denom_rows = metrics["denominations"] or [["1000", "0", "0", "0"], ["500", "0", "0", "0"], ["200", "0", "0", "0"], ["100", "0", "0", "0"], ["50", "0", "0", "0"], ["20", "0", "0", "0"], ["10", "0", "0", "0"], ["5", "0", "0", "0"], ["1", "0", "0", "0"]]
    _write_block(
        sheet_api,
        spreadsheet_id,
        tab_name,
        f"A16:D{15 + len(denom_rows)}",
        denom_rows,
    )

    _style_day_tab(
        service,
        spreadsheet_id,
        tab_name,
        sales_rows_count=len(sales_rows),
    )


def get_google_sheets_sync_status() -> dict[str, Any]:
    sync_config = _get_google_sync_config()
    raw_json = (sync_config.get("service_account_json") or "").strip()
    json_path = (sync_config.get("service_account_file") or "").strip()

    status: dict[str, Any] = {
        "enabled": bool(sync_config.get("enabled")),
        "sub_spreadsheet_id": sync_config.get("sub_spreadsheet_id", ""),
        "main_spreadsheet_id": sync_config.get("main_spreadsheet_id", ""),
        "sync_scope": sync_config.get("sync_scope", "sub"),
        "credential_configured": bool(raw_json or json_path),
        "connection_ok": False,
        "message": "",
    }

    if raw_json:
        try:
            json.loads(raw_json)
        except Exception as exc:
            status["message"] = f"Service account JSON is invalid: {exc}"
            return status

    checks = []
    for stall_type in _scope_stall_types(sync_config.get("sync_scope", "sub")):
        spreadsheet_id = _spreadsheet_id_for_stall(sync_config, stall_type)
        service, sheet_api, init_error = _get_sheets_clients(sync_config, spreadsheet_id)
        if service is None or sheet_api is None:
            checks.append(f"{stall_type}: {init_error}")
            continue

        try:
            today_tab = _daily_tab_name(timezone.localdate())
            _ensure_tab(service, spreadsheet_id, today_tab)
            _write_block(sheet_api, spreadsheet_id, today_tab, "A1:A1", [["SYNC READY"]])
            checks.append(f"{stall_type}: ok")
        except Exception as exc:
            logger.exception("Google Sheets status check failed for %s: %s", stall_type, exc)
            checks.append(f"{stall_type}: {exc}")

    status["connection_ok"] = all(c.endswith("ok") for c in checks)
    status["message"] = " | ".join(checks) if checks else "No scope selected"
    return status


def sync_sales_day_to_google_sheet(stall_id: int, target_date: date) -> bool:
    sync_config = _get_google_sync_config()
    if not sync_config.get("enabled"):
        return False

    try:
        stall = Stall.objects.get(pk=stall_id)
    except Stall.DoesNotExist:
        logger.warning("Google Sheets day sync skipped: stall %s does not exist", stall_id)
        return False

    spreadsheet_id = _spreadsheet_id_for_stall(sync_config, stall.stall_type)
    service, sheet_api, init_error = _get_sheets_clients(sync_config, spreadsheet_id)
    if service is None or sheet_api is None:
        logger.warning("Google Sheets day sync skipped: %s", init_error)
        return False

    try:
        _render_day_tab(service, sheet_api, spreadsheet_id, stall, target_date)
        return True
    except Exception as exc:
        logger.exception(
            "Google Sheets day sync failed for stall=%s date=%s: %s",
            stall_id,
            target_date,
            exc,
        )
        return False


def sync_historical_sales_to_google_sheets(
    limit: int | None = None,
    start_date=None,
    end_date=None,
) -> dict[str, Any]:
    sync_config = _get_google_sync_config()
    if not sync_config.get("enabled"):
        return {
            "ok": False,
            "message": "Google Sheets sync is disabled",
            "synced": 0,
            "failed": 0,
            "considered": 0,
            "errors": [],
        }

    stall_types = _scope_stall_types(sync_config.get("sync_scope", "sub"))
    stalls = Stall.objects.filter(stall_type__in=stall_types, is_deleted=False)

    day_targets = set()

    sales_qs = (
        SalesTransaction.objects.select_related("stall")
        .annotate(effective_date=Coalesce("transaction_date", TruncDate("created_at")))
        .filter(stall__in=stalls)
        .filter(voided=False, is_deleted=False)
    )
    if start_date:
        sales_qs = sales_qs.filter(effective_date__gte=start_date)
    if end_date:
        sales_qs = sales_qs.filter(effective_date__lte=end_date)

    for tx in sales_qs.order_by("id"):
        day_targets.add((tx.stall_id, tx.effective_date))

    remit_qs = RemittanceRecord.objects.filter(stall__in=stalls)
    if start_date:
        remit_qs = remit_qs.filter(remittance_date__gte=start_date)
    if end_date:
        remit_qs = remit_qs.filter(remittance_date__lte=end_date)
    for rem in remit_qs:
        if rem.remittance_date:
            day_targets.add((rem.stall_id, rem.remittance_date))

    exp_qs = Expense.objects.filter(stall__in=stalls, is_deleted=False)
    if start_date:
        exp_qs = exp_qs.filter(expense_date__gte=start_date)
    if end_date:
        exp_qs = exp_qs.filter(expense_date__lte=end_date)
    for expense in exp_qs:
        if expense.expense_date:
            day_targets.add((expense.stall_id, expense.expense_date))

    ordered_targets = sorted(day_targets, key=lambda x: (x[0], x[1]))
    if isinstance(limit, int) and limit > 0:
        ordered_targets = ordered_targets[:limit]

    synced = 0
    failed = 0
    errors: list[str] = []

    for stall_id, target_date in ordered_targets:
        ok = sync_sales_day_to_google_sheet(stall_id, target_date)
        if ok:
            synced += 1
        else:
            failed += 1
            errors.append(f"stall={stall_id}, date={target_date}")

    return {
        "ok": failed == 0,
        "message": "Historical sync completed" if failed == 0 else "Historical sync completed with errors",
        "synced": synced,
        "failed": failed,
        "considered": synced + failed,
        "errors": errors[:20],
    }


def sync_sales_transaction_to_google_sheet(transaction_id: int) -> bool:
    sync_config = _get_google_sync_config()
    if not sync_config.get("enabled"):
        return False

    try:
        transaction = SalesTransaction.objects.select_related("stall").get(pk=transaction_id)
    except SalesTransaction.DoesNotExist:
        logger.warning("Google Sheets sync skipped: SalesTransaction %s does not exist", transaction_id)
        return False

    if not transaction.stall:
        return False

    return sync_sales_day_to_google_sheet(transaction.stall_id, _effective_date(transaction))

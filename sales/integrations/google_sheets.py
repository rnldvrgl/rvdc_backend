import importlib
import json
import logging
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from expenses.models import Expense
from inventory.models import Stall
from remittances.models import RemittanceRecord
from sales.models import PaymentStatus, SalesPayment, SalesTransaction, StallMonthlySheet

logger = logging.getLogger(__name__)


def _is_rate_limited_error(exc: Exception) -> bool:
    resp = getattr(exc, "resp", None)
    status_code = getattr(resp, "status", None)
    if status_code == 429:
        return True

    text = str(exc)
    return "RATE_LIMIT_EXCEEDED" in text or "quota" in text.lower()


def _execute_with_backoff(request, operation: str, max_attempts: int = 5):
    for attempt in range(max_attempts):
        try:
            return request.execute()
        except Exception as exc:
            is_last_attempt = attempt >= max_attempts - 1
            if not _is_rate_limited_error(exc) or is_last_attempt:
                raise

            delay_seconds = min(16.0, float(2 ** attempt))
            logger.warning(
                "Google Sheets rate limit hit during %s (attempt %s/%s). Retrying in %.1fs",
                operation,
                attempt + 1,
                max_attempts,
                delay_seconds,
            )
            time.sleep(delay_seconds)


def _normalize_google_error_text(error_text: str) -> str:
    text = (error_text or "").strip()
    lower_text = text.lower()

    if "rate_limit_exceeded" in lower_text or "quota exceeded" in lower_text or "write requests per minute" in lower_text:
        return "Google Sheets write quota reached. Please wait about 1-2 minutes and retry."

    if "403" in text or "does not have permission" in lower_text or "insufficient" in lower_text or "forbidden" in lower_text:
        return "Permission denied. Ensure the service account has access to this spreadsheet."

    return text.split("\n", 1)[0][:240] if text else "Google Sheets sync failed"


def _get_google_sync_config() -> dict:
    config = {
        "enabled": bool(getattr(settings, "GOOGLE_SHEETS_SYNC_ENABLED", False)),
        "sub_spreadsheet_id": getattr(settings, "GOOGLE_SHEETS_SPREADSHEET_ID", "").strip(),
        "main_spreadsheet_id": getattr(settings, "GOOGLE_SHEETS_MAIN_SPREADSHEET_ID", "").strip(),
        "sync_scope": getattr(settings, "GOOGLE_SHEETS_SUB_STALL_TYPE", "sub"),
        "share_email": getattr(settings, "GOOGLE_SHEETS_SHARE_EMAIL", "").strip(),
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
        config["share_email"] = (
            getattr(system_settings, "google_sheets_share_email", "") or ""
        ).strip()
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

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

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


def _month_key_for_date(target_date: date) -> str:
    return target_date.strftime("%Y-%m")


def _resolve_monthly_sheet(stall: Stall, target_date: date) -> StallMonthlySheet | None:
    return (
        StallMonthlySheet.objects.filter(
            stall=stall,
            month_key=_month_key_for_date(target_date),
            is_active=True,
        )
        .order_by("-updated_at", "-id")
        .first()
    )


def _resolve_spreadsheet_target(sync_config: dict, stall: Stall, target_date: date) -> tuple[str, StallMonthlySheet | None]:
    monthly_sheet = _resolve_monthly_sheet(stall, target_date)
    if monthly_sheet and monthly_sheet.spreadsheet_id:
        return monthly_sheet.spreadsheet_id.strip(), monthly_sheet
    return _spreadsheet_id_for_stall(sync_config, stall.stall_type), None


def _verify_service_account_access(sync_config: dict, spreadsheet_id: str) -> tuple[bool, str]:
    """Check if service account has read access to a spreadsheet."""
    if not spreadsheet_id:
        return False, "Spreadsheet ID is missing"

    credentials = _get_service_account_credentials(sync_config)
    if credentials is None:
        return False, "Service account credentials are not configured or invalid"

    try:
        discovery_module = importlib.import_module("googleapiclient.discovery")
        build = discovery_module.build
        service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        # Simple read-only check to verify access
        _execute_with_backoff(
            service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                fields="spreadsheetId",
            ),
            operation=f"verify service account access {spreadsheet_id}",
        )
        return True, ""
    except Exception as exc:
        text = str(exc)
        http_status = getattr(getattr(exc, "resp", None), "status", None)

        if http_status == 404:
            return False, "Spreadsheet not found"
        if http_status == 403:
            sa_email = getattr(credentials, "service_account_email", "the configured service account")
            return False, f"Service account ({sa_email}) does not have access to this spreadsheet"

        lower_text = text.lower()
        if "does not have permission" in lower_text or "forbidden" in lower_text:
            sa_email = getattr(credentials, "service_account_email", "the configured service account")
            return False, f"Service account ({sa_email}) does not have access to this spreadsheet"

        logger.debug("Failed to verify service account access to %s: %s", spreadsheet_id, exc)
        return False, _normalize_google_error_text(text)


def _share_sheet_with_email(sync_config: dict, spreadsheet_id: str, email: str) -> tuple[bool, str]:
    cleaned_email = (email or "").strip()
    if not cleaned_email:
        return False, "Share email is empty"

    credentials = _get_service_account_credentials(sync_config)
    if credentials is None:
        return False, "Service account credentials are not configured or invalid"

    try:
        discovery_module = importlib.import_module("googleapiclient.discovery")
        build = discovery_module.build
        drive_service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        _execute_with_backoff(
            drive_service.permissions().create(
                fileId=spreadsheet_id,
                body={
                    "type": "user",
                    "role": "writer",
                    "emailAddress": cleaned_email,
                },
                sendNotificationEmail=False,
            ),
            operation=f"drive.permissions.create {spreadsheet_id}",
        )
        return True, ""
    except Exception as exc:
        text = str(exc)

        # Extract HTTP status code from the exception
        http_status = getattr(getattr(exc, "resp", None), "status", None)

        # 409 usually means permission already exists.
        if "already" in text.lower() and "permission" in text.lower():
            return True, ""

        # Check for 403 Forbidden or permission-related errors
        lower_text = text.lower()
        if http_status == 403 or "does not have permission" in lower_text or "insufficient" in lower_text or "forbidden" in lower_text:
            sa_email = getattr(credentials, "service_account_email", "the configured service account")
            return (
                False,
                f"Service account has no access to this spreadsheet. Share the sheet with {sa_email} first, then retry sync.",
            )

        logger.warning("Failed sharing spreadsheet=%s to %s: %s", spreadsheet_id, cleaned_email, exc)
        return False, _normalize_google_error_text(text)


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


def _inclusive_date_range(start_date: date, end_date: date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def _a1_range(worksheet_name: str, a1_notation: str) -> str:
    escaped = (worksheet_name or "").replace("'", "''")
    return f"'{escaped}'!{a1_notation}"


def _daily_tab_name(target_date: date) -> str:
    return target_date.strftime("%B %d").upper()


def _day_sync_lock_key(spreadsheet_id: str, tab_name: str) -> str:
    return f"google_sheets_day_sync_lock:{spreadsheet_id}:{tab_name}"


def _acquire_day_sync_lock(spreadsheet_id: str, tab_name: str, timeout: int = 180) -> str | None:
    lock_key = _day_sync_lock_key(spreadsheet_id, tab_name)
    if cache.add(lock_key, True, timeout=timeout):
        return lock_key
    return None


def _release_day_sync_lock(lock_key: str | None) -> None:
    if lock_key:
        cache.delete(lock_key)


def _parse_daily_tab_date(title: str, today: date) -> date | None:
    """Parse tab titles like 'APRIL 22' into a comparable date near today."""
    raw = (title or "").strip()
    if not raw:
        return None

    normalized = raw.title()
    parsed = None

    # Try common daily tab formats used in monthly sheets.
    # Examples: "APRIL 29", "APR 29", "APRIL 29, 2026", "APR 29, 2026"
    for fmt in ("%B %d", "%b %d", "%B %d, %Y", "%b %d, %Y"):
        try:
            candidate = datetime.strptime(normalized, fmt).date()
            if "%Y" not in fmt:
                candidate = candidate.replace(year=today.year)
            parsed = candidate
            break
        except Exception:
            continue

    if parsed is None:
        return None

    # Keep parsed date aligned around today across year boundaries.
    if (parsed - today).days > 180:
        parsed = parsed.replace(year=today.year - 1)
    elif (today - parsed).days > 180:
        parsed = parsed.replace(year=today.year + 1)
    return parsed


def _latest_daily_tab_gid(sheets: list[dict[str, Any]]) -> int | None:
    today = timezone.localdate()
    latest_gid: int | None = None
    latest_date: date | None = None

    for sheet in sheets or []:
        props = sheet.get("properties", {})
        title = props.get("title", "")
        sheet_id = props.get("sheetId")
        if sheet_id is None:
            continue

        parsed = _parse_daily_tab_date(title, today)
        if parsed is None:
            continue

        if latest_date is None or parsed > latest_date:
            latest_date = parsed
            latest_gid = int(sheet_id)

    return latest_gid


def _current_daily_tab_gid(
    sheets: list[dict[str, Any]],
    target_date: date | None = None,
) -> int | None:
    target_date = target_date or timezone.localdate()
    exact_gid: int | None = None
    fallback_gid: int | None = None
    fallback_date: date | None = None

    for sheet in sheets or []:
        props = sheet.get("properties", {})
        title = props.get("title", "")
        sheet_id = props.get("sheetId")
        if sheet_id is None:
            continue

        parsed = _parse_daily_tab_date(title, target_date)
        if parsed is None:
            continue

        if parsed == target_date:
            exact_gid = int(sheet_id)
            break

        if (
            parsed.year == target_date.year
            and parsed.month == target_date.month
            and parsed <= target_date
            and (fallback_date is None or parsed > fallback_date)
        ):
            fallback_date = parsed
            fallback_gid = int(sheet_id)

    return exact_gid if exact_gid is not None else fallback_gid


def _effective_date(transaction: SalesTransaction) -> date:
    if transaction.transaction_date:
        return transaction.transaction_date
    return timezone.localtime(transaction.created_at).date()


def _serialize_decimal(value) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, (int, float)):
        return f"{Decimal(str(value)):.2f}"
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


def _build_sales_rows(transactions, stall_type: str = "sub") -> list[list[str]]:
    rows: list[list[str]] = []

    # For main stall, build service lookup map
    service_map = {}
    if stall_type == "main":
        from services.models import Service
        services = Service.objects.filter(
            related_transaction__in=transactions
        ).prefetch_related("technician_assignments__technician")
        for svc in services:
            if svc.related_transaction_id:
                service_map[svc.related_transaction_id] = svc

    for transaction in transactions:
        client_name = transaction.client.full_name if transaction.client else ""
        receipt_number = transaction.manual_receipt_number or ""
        book_number = transaction.receipt_book or ""
        payment_method = _payment_method_label(transaction)

        # Get service info if main stall
        service_type = ""
        technicians = ""
        if stall_type == "main" and transaction.id in service_map:
            svc = service_map[transaction.id]
            service_type = svc.get_service_type_display() if hasattr(svc, 'get_service_type_display') else svc.service_type or ""
            tech_names = [
                ta.technician.get_full_name()
                for ta in svc.technician_assignments.all()
            ]
            technicians = ", ".join(tech_names) if tech_names else ""

        line_rows = []
        for line in transaction.items.all():
            description = _normalize_line_description(line)
            quantity = _serialize_decimal(line.quantity)
            amount = _serialize_decimal(line.line_total)
            if stall_type == "main":
                line_rows.append([
                    quantity,
                    description,
                    amount,
                    client_name,
                    book_number,
                    receipt_number,
                    service_type,
                    technicians,
                    payment_method,
                ])
            else:
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
            if stall_type == "main":
                line_rows.append([
                    "",
                    transaction.note or "",
                    _serialize_decimal(transaction.computed_total),
                    client_name,
                    book_number,
                    receipt_number,
                    service_type,
                    technicians,
                    payment_method,
                ])
            else:
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
        .select_related("category")
        .order_by("id")
    )

    rows: list[list[str]] = []
    for expense in expenses:
        category_name = expense.category.name if expense.category else "Uncategorized"
        vendor_name = (expense.vendor or "").strip()
        description = (expense.description or "").strip()
        amount = expense.paid_amount or Decimal("0")
        if expense.is_reimbursement:
            amount = -amount
        rows.append([category_name, vendor_name, description, _serialize_decimal(amount)])

    return rows


def _get_day_metrics(stall: Stall, target_date: date) -> dict[str, Any]:
    remittance = (
        RemittanceRecord.objects.select_related("cash_breakdown")
        .filter(stall=stall, remittance_date=target_date)
        .first()
    )

    def sum_sales(payment_type: str) -> Decimal:
        total_payments = (
            SalesPayment.objects.filter(
                transaction__stall=stall,
                payment_date__date=target_date,
                transaction__payment_status__in=[PaymentStatus.PAID, PaymentStatus.PARTIAL],
                transaction__voided=False,
                transaction__is_deleted=False,
                payment_type=payment_type,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0")
        )

        if payment_type == "cash":
            total_change = (
                SalesTransaction.objects.filter(
                    stall=stall,
                    payment_status__in=[PaymentStatus.PAID, PaymentStatus.PARTIAL],
                    voided=False,
                    is_deleted=False,
                    payments__payment_type="cash",
                    payments__payment_date__date=target_date,
                )
                .distinct()
                .aggregate(total=Sum("change_amount"))["total"]
                or Decimal("0")
            )
            return total_payments - total_change

        return total_payments

    live_sales = {pt: sum_sales(pt) for pt in ["cash", "gcash", "credit", "debit", "cheque"]}

    metrics = {
        "total_cash_sales": live_sales["cash"],
        "total_gcash_sales": live_sales["gcash"],
        "total_credit_sales": live_sales["credit"],
        "total_debit_sales": live_sales["debit"],
        "total_cheque_sales": live_sales["cheque"],
        "total_expenses": Decimal("0"),
        "cod_for_today": Decimal("0"),
        "cod_for_next_day": Decimal("0"),
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

    cash_sales = live_sales["cash"]
    live_expected = max(Decimal("0"), cash_sales + metrics["cod_for_today"] - expense_total)
    metrics["expected_remittance"] = live_expected

    if remittance:
        metrics["total_expenses"] = remittance.total_expenses or Decimal("0")
        metrics["remitted_amount"] = Decimal(str(remittance.remitted_amount or 0))
        metrics["declared_amount"] = Decimal(str(remittance.declared_amount or 0))
        metrics["balance"] = remittance.balance or Decimal("0")
        if hasattr(remittance, "cash_breakdown"):
            metrics["cod_for_next_day"] = Decimal(str(remittance.cash_breakdown.cod_amount or 0))

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
    request = sheet_api.update(
        spreadsheetId=spreadsheet_id,
        range=_a1_range(tab_name, a1),
        valueInputOption="USER_ENTERED",
        body={"values": values},
    )
    _execute_with_backoff(request, operation=f"values.update {tab_name}!{a1}")


def _write_blocks(sheet_api, spreadsheet_id: str, tab_name: str, blocks: list[dict[str, Any]]):
    if not blocks:
        return

    data = [
        {
            "range": _a1_range(tab_name, block["a1"]),
            "values": block["values"],
        }
        for block in blocks
    ]

    request = sheet_api.batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "valueInputOption": "USER_ENTERED",
            "data": data,
        },
    )
    _execute_with_backoff(request, operation=f"values.batchUpdate {tab_name}")


def _ensure_tab(service, spreadsheet_id: str, tab_name: str):
    metadata = _execute_with_backoff(
        service.spreadsheets().get(spreadsheetId=spreadsheet_id),
        operation="spreadsheets.get metadata",
    )
    existing_titles = {
        sheet.get("properties", {}).get("title")
        for sheet in metadata.get("sheets", [])
    }

    if tab_name not in existing_titles:
        _execute_with_backoff(
            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
            ),
            operation=f"spreadsheets.batchUpdate addSheet {tab_name}",
        )


def _clear_day_tab(sheet_api, spreadsheet_id: str, tab_name: str):
    request = sheet_api.clear(
        spreadsheetId=spreadsheet_id,
        range=_a1_range(tab_name, "A1:Z200"),
        body={},
    )
    _execute_with_backoff(request, operation=f"values.clear {tab_name}!A1:Z200")


def _style_day_tab(
    service,
    spreadsheet_id: str,
    tab_name: str,
    sales_rows_count: int,
    expense_rows_count: int = 0,
    stall_type: str = "sub",
    over_short_value: Decimal | float | int | None = None,
):
    metadata = _execute_with_backoff(
        service.spreadsheets().get(spreadsheetId=spreadsheet_id),
        operation="spreadsheets.get style metadata",
    )
    sheet_id = None
    row_count = 1000
    col_count = 26
    for sheet in metadata.get("sheets", []):
        props = sheet.get("properties", {})
        if props.get("title") == tab_name:
            sheet_id = props.get("sheetId")
            grid_props = props.get("gridProperties", {})
            row_count = int(grid_props.get("rowCount") or row_count)
            col_count = int(grid_props.get("columnCount") or col_count)
            break

    if sheet_id is None:
        return

    sales_end_row = max(4, 4 + sales_rows_count)
    sales_data_cols = 9 if stall_type == "main" else 7
    summary_start_col = 11 if stall_type == "main" else 9
    remittance_end_col = summary_start_col + 2  # 2 columns: label + amount
    cash_end_col = summary_start_col + 4  # 4 columns: denomination, remitted, declared, cod
    expenses_end_col = summary_start_col + 4  # 4 columns: category, vendor, description, amount

    requests = []

    # Set column widths
    # Column B (Description) = 240
    # Column D (Client Name) = 200
    # Column H (Technicians, main stall only) = 200
    # Remittance label column = 160
    # Expenses description column = 145
    requests.extend([
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 1,  # Column B
                    "endIndex": 2,
                },
                "properties": {"pixelSize": 240},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 3,  # Column D
                    "endIndex": 4,
                },
                "properties": {"pixelSize": 200},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 7,  # Column H (Technicians)
                    "endIndex": 8,
                },
                "properties": {"pixelSize": 200},
                "fields": "pixelSize",
            }
        } if stall_type == "main" else None,
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": summary_start_col,
                    "endIndex": summary_start_col + 1,
                },
                "properties": {"pixelSize": 160},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": summary_start_col + 1,
                    "endIndex": summary_start_col + 2,
                },
                "properties": {"pixelSize": 145},
                "fields": "pixelSize",
            }
        },
    ])
    requests = [request for request in requests if request is not None]

    # Global alignment baseline for both main and sub tabs.
    # Specific style blocks can still override this when needed.
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": 200,
                "startColumnIndex": 0,
                "endColumnIndex": 26,
            },
            "cell": {
                "userEnteredFormat": {
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                }
            },
            "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment)",
        }
    })

    # Reset side-panel staging area to remove stale legacy fills/borders from prior layouts.
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": 200,
                "startColumnIndex": 8,  # Column I
                "endColumnIndex": 17,   # Through column Q
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": 1, "green": 1, "blue": 1},
                    "textFormat": {
                        "foregroundColor": {"red": 0, "green": 0, "blue": 0},
                        "bold": False,
                    },
                    "borders": {
                        "left": {"style": "NONE"},
                        "right": {"style": "NONE"},
                        "top": {"style": "NONE"},
                        "bottom": {"style": "NONE"},
                    },
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,borders)",
        }
    })

    # Keep visible light-gray grid borders in spacer columns between sales and side panel.
    spacer_start_col = sales_data_cols - 1 if stall_type == "main" else sales_data_cols
    if summary_start_col > spacer_start_col:
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 3,
                    "endRowIndex": 200,
                    "startColumnIndex": spacer_start_col,
                    "endColumnIndex": summary_start_col,
                },
                "cell": {
                    "userEnteredFormat": {
                        "borders": {
                            "left": {
                                "style": "SOLID",
                                "color": {"red": 0.82, "green": 0.82, "blue": 0.82},
                            },
                            "right": {
                                "style": "SOLID",
                                "color": {"red": 0.82, "green": 0.82, "blue": 0.82},
                            },
                            "top": {
                                "style": "SOLID",
                                "color": {"red": 0.82, "green": 0.82, "blue": 0.82},
                            },
                            "bottom": {
                                "style": "SOLID",
                                "color": {"red": 0.82, "green": 0.82, "blue": 0.82},
                            },
                        }
                    }
                },
                "fields": "userEnteredFormat.borders",
            }
        })

    # Unmerge all merged cells in the tab first.
    # This avoids partial-overlap errors from historical layouts.
    requests.append({
        "unmergeCells": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": row_count,
                "startColumnIndex": 0,
                "endColumnIndex": col_count,
            }
        }
    })

    # Merge cells
    requests.extend([
        {
            "mergeCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": sales_data_cols,
                },
                "mergeType": "MERGE_ALL",
            }
        },
        {
            "mergeCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": 2,
                    "startColumnIndex": 0,
                    "endColumnIndex": sales_data_cols,
                },
                "mergeType": "MERGE_ALL",
            }
        },
        {
            "mergeCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": summary_start_col,
                    "endColumnIndex": remittance_end_col,
                },
                "mergeType": "MERGE_ALL",
            }
        },
        {
            "mergeCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 14,
                    "endRowIndex": 15,
                    "startColumnIndex": summary_start_col,
                    "endColumnIndex": cash_end_col,
                },
                "mergeType": "MERGE_ALL",
            }
        },
        {
            "mergeCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 26,
                    "endRowIndex": 27,
                    "startColumnIndex": summary_start_col,
                    "endColumnIndex": expenses_end_col,
                },
                "mergeType": "MERGE_ALL",
            }
        },
    ])

    # Title row (row 1) - Dark background with white bold text
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": 1,
                "startColumnIndex": 0,
                "endColumnIndex": sales_data_cols,
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": 0.09, "green": 0.20, "blue": 0.32},
                    "horizontalAlignment": "CENTER",
                    "textFormat": {
                        "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                        "fontSize": 15,
                        "bold": True,
                    },
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }
    })

    # Subtitle row (row 2) - Light blue background with bold text
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,
                "endRowIndex": 2,
                "startColumnIndex": 0,
                "endColumnIndex": sales_data_cols,
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": 0.94, "green": 0.97, "blue": 0.99},
                    "horizontalAlignment": "CENTER",
                    "textFormat": {
                        "foregroundColor": {"red": 0.12, "green": 0.22, "blue": 0.33},
                        "fontSize": 11,
                        "bold": True,
                    },
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }
    })

    # Sales header row (row 4) - Bold with light blue background and borders
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 3,
                "endRowIndex": 4,
                "startColumnIndex": 0,
                "endColumnIndex": sales_data_cols,
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": 0.92, "green": 0.95, "blue": 0.98},
                    "textFormat": {"bold": True},
                    "horizontalAlignment": "CENTER",
                    "borders": {
                        "left": {"style": "SOLID"},
                        "right": {"style": "SOLID"},
                        "top": {"style": "SOLID"},
                        "bottom": {"style": "SOLID"},
                    },
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,borders)",
        }
    })

    # Sales data rows - borders
    if sales_rows_count > 0:
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 4,
                    "endRowIndex": sales_end_row,
                    "startColumnIndex": 0,
                    "endColumnIndex": sales_data_cols,
                },
                "cell": {
                    "userEnteredFormat": {
                        "borders": {
                            "left": {"style": "SOLID"},
                            "right": {"style": "SOLID"},
                            "top": {"style": "SOLID"},
                            "bottom": {"style": "SOLID"},
                        },
                        "wrapStrategy": "WRAP",
                    }
                },
                "fields": "userEnteredFormat(borders,wrapStrategy)",
            }
        })

    # REMITTANCES SUMMARY header (row 1, 2 columns)
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": 1,
                "startColumnIndex": summary_start_col,
                "endColumnIndex": remittance_end_col,
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": 0.10, "green": 0.16, "blue": 0.24},
                    "horizontalAlignment": "CENTER",
                    "textFormat": {
                        "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                        "fontSize": 13,
                        "bold": True,
                    },
                    "borders": {
                        "left": {"style": "SOLID"},
                        "right": {"style": "SOLID"},
                        "top": {"style": "SOLID"},
                        "bottom": {"style": "SOLID"},
                    },
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,borders)",
        }
    })

    # Remittance labels (rows 2-13, first column) - bold + borders
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,
                "endRowIndex": 13,
                "startColumnIndex": summary_start_col,
                "endColumnIndex": summary_start_col + 1,
            },
            "cell": {
                "userEnteredFormat": {
                    "textFormat": {"bold": True},
                    "borders": {
                        "left": {"style": "SOLID"},
                        "right": {"style": "SOLID"},
                        "top": {"style": "SOLID"},
                        "bottom": {"style": "SOLID"},
                    },
                }
            },
            "fields": "userEnteredFormat(textFormat,borders)",
        }
    })

    # Remittance values (rows 2-13, amount column) - centered + borders
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,
                "endRowIndex": 13,
                "startColumnIndex": summary_start_col + 1,
                "endColumnIndex": summary_start_col + 2,
            },
            "cell": {
                "userEnteredFormat": {
                    "horizontalAlignment": "CENTER",
                    "borders": {
                        "left": {"style": "SOLID"},
                        "right": {"style": "SOLID"},
                        "top": {"style": "SOLID"},
                        "bottom": {"style": "SOLID"},
                    },
                }
            },
            "fields": "userEnteredFormat(horizontalAlignment,borders)",
        }
    })

    # Currency format for remittance amount column (Peso).
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,
                "endRowIndex": 13,
                "startColumnIndex": summary_start_col + 1,
                "endColumnIndex": summary_start_col + 2,
            },
            "cell": {
                "userEnteredFormat": {
                    "numberFormat": {
                        "type": "CURRENCY",
                        "pattern": "\"PHP\" #,##0.00",
                    }
                }
            },
            "fields": "userEnteredFormat.numberFormat",
        }
    })

    # CASH / COINS BREAKDOWN header (row 15, 4 columns)
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 14,
                "endRowIndex": 15,
                "startColumnIndex": summary_start_col,
                "endColumnIndex": cash_end_col,
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": 0.11, "green": 0.24, "blue": 0.18},
                    "horizontalAlignment": "CENTER",
                    "textFormat": {
                        "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                        "fontSize": 12,
                        "bold": True,
                    },
                    "borders": {
                        "left": {"style": "SOLID"},
                        "right": {"style": "SOLID"},
                        "top": {"style": "SOLID"},
                        "bottom": {"style": "SOLID"},
                    },
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,borders)",
        }
    })

    # Denominations header row (row 16, 4 columns) - bold labels + borders
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 15,
                "endRowIndex": 16,
                "startColumnIndex": summary_start_col,
                "endColumnIndex": cash_end_col,
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": 0.92, "green": 0.95, "blue": 0.98},
                    "textFormat": {"bold": True},
                    "horizontalAlignment": "CENTER",
                    "borders": {
                        "left": {"style": "SOLID"},
                        "right": {"style": "SOLID"},
                        "top": {"style": "SOLID"},
                        "bottom": {"style": "SOLID"},
                    },
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,borders)",
        }
    })

    # Denominations data rows (rows 17-25, 4 columns) - RED denomination labels + borders
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 16,
                "endRowIndex": 25,
                "startColumnIndex": summary_start_col,
                "endColumnIndex": cash_end_col,
            },
            "cell": {
                "userEnteredFormat": {
                    "borders": {
                        "left": {"style": "SOLID"},
                        "right": {"style": "SOLID"},
                        "top": {"style": "SOLID"},
                        "bottom": {"style": "SOLID"},
                    },
                    "horizontalAlignment": "CENTER",
                }
            },
            "fields": "userEnteredFormat(borders,horizontalAlignment)",
        }
    })

    # First column of denomination rows (denomination labels) - RED COLOR
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 16,
                "endRowIndex": 25,
                "startColumnIndex": summary_start_col,
                "endColumnIndex": summary_start_col + 1,
            },
            "cell": {
                "userEnteredFormat": {
                    "textFormat": {
                        "bold": True,
                        "foregroundColor": {"red": 0.85, "green": 0.0, "blue": 0.0},
                    },
                    "borders": {
                        "left": {"style": "SOLID"},
                        "right": {"style": "SOLID"},
                        "top": {"style": "SOLID"},
                        "bottom": {"style": "SOLID"},
                    },
                }
            },
            "fields": "userEnteredFormat(textFormat,borders)",
        }
    })

    # EXPENSES header (row 27, cols J-L) - RED BACKGROUND + WHITE TEXT
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 26,
                "endRowIndex": 27,
                "startColumnIndex": summary_start_col,
                "endColumnIndex": expenses_end_col,
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": 0.85, "green": 0.0, "blue": 0.0},
                    "horizontalAlignment": "CENTER",
                    "textFormat": {
                        "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                        "fontSize": 12,
                        "bold": True,
                    },
                    "borders": {
                        "left": {"style": "SOLID"},
                        "right": {"style": "SOLID"},
                        "top": {"style": "SOLID"},
                        "bottom": {"style": "SOLID"},
                    },
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,borders)",
        }
    })

    # Expenses header row (row 28, cols J-L) - bold labels + light blue background + borders
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 27,
                "endRowIndex": 28,
                "startColumnIndex": summary_start_col,
                "endColumnIndex": expenses_end_col,
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": 0.92, "green": 0.95, "blue": 0.98},
                    "textFormat": {"bold": True},
                    "horizontalAlignment": "CENTER",
                    "borders": {
                        "left": {"style": "SOLID"},
                        "right": {"style": "SOLID"},
                        "top": {"style": "SOLID"},
                        "bottom": {"style": "SOLID"},
                    },
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,borders)",
        }
    })

    # Expense data rows (row 29 onward) - apply borders only to actual rows.
    if expense_rows_count > 0:
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 28,
                    "endRowIndex": 28 + expense_rows_count,
                    "startColumnIndex": summary_start_col,
                    "endColumnIndex": expenses_end_col,
                },
                "cell": {
                    "userEnteredFormat": {
                        "borders": {
                            "left": {"style": "SOLID"},
                            "right": {"style": "SOLID"},
                            "top": {"style": "SOLID"},
                            "bottom": {"style": "SOLID"},
                        },
                        "wrapStrategy": "WRAP",
                    }
                },
                "fields": "userEnteredFormat(borders,wrapStrategy)",
            }
        })

    # Currency format for sales amount column C (rows below header).
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 4,
                "endRowIndex": max(5, sales_end_row),
                "startColumnIndex": 2,
                "endColumnIndex": 3,
            },
            "cell": {
                "userEnteredFormat": {
                    "numberFormat": {
                        "type": "CURRENCY",
                        "pattern": "\"PHP\" #,##0.00",
                    }
                }
            },
            "fields": "userEnteredFormat.numberFormat",
        }
    })

    # Currency format for expenses amount column (3rd col in expenses block).
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 28,
                "endRowIndex": 200,
                "startColumnIndex": summary_start_col + 2,
                "endColumnIndex": summary_start_col + 3,
            },
            "cell": {
                "userEnteredFormat": {
                    "numberFormat": {
                        "type": "CURRENCY",
                        "pattern": "\"PHP\" #,##0.00",
                    }
                }
            },
            "fields": "userEnteredFormat.numberFormat",
        }
    })

    # Over/Short value (summary row 13) is highlighted based on sign.
    over_short_number = Decimal(str(over_short_value or 0))
    if over_short_number > 0:
        over_short_bg = {"red": 0.86, "green": 0.95, "blue": 0.89}
        over_short_fg = {"red": 0.11, "green": 0.46, "blue": 0.2}
    elif over_short_number < 0:
        over_short_bg = {"red": 0.98, "green": 0.89, "blue": 0.89}
        over_short_fg = {"red": 0.73, "green": 0.11, "blue": 0.11}
    else:
        over_short_bg = {"red": 1, "green": 1, "blue": 1}
        over_short_fg = {"red": 0, "green": 0, "blue": 0}

    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 12,
                "endRowIndex": 13,
                "startColumnIndex": summary_start_col + 1,
                "endColumnIndex": summary_start_col + 2,
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": over_short_bg,
                    "textFormat": {
                        "foregroundColor": over_short_fg,
                        "bold": True,
                    },
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat)",
        }
    })

    # Basic filter
    requests.append({
        "setBasicFilter": {
            "filter": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 3,
                    "endRowIndex": sales_end_row,
                    "startColumnIndex": 0,
                    "endColumnIndex": sales_data_cols,
                }
            }
        }
    })

    # Update sheet properties
    requests.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": 0},
            },
            "fields": "gridProperties.frozenRowCount",
        }
    })

    _execute_with_backoff(
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests},
        ),
        operation=f"spreadsheets.batchUpdate style {tab_name}",
    )


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
        .filter(
            Q(effective_date=target_date)
            | Q(payments__payment_date__date=target_date)
        )
        .distinct()
        .order_by("manual_receipt_number", "id")
    )

    day_transactions: list[SalesTransaction] = []
    for transaction in transactions:
        payment_dates = {
            payment.payment_date.date()
            for payment in transaction.payments.all()
            if payment.payment_date
        }

        if payment_dates:
            if target_date in payment_dates:
                day_transactions.append(transaction)
            continue

        if _effective_date(transaction) == target_date:
            day_transactions.append(transaction)

    sales_rows = _build_sales_rows(day_transactions, stall.stall_type)
    expense_rows = _get_expense_rows(stall, target_date)
    metrics = _get_day_metrics(stall, target_date)

    stall_label = "MAIN STALL" if stall.stall_type == "main" else "SUB STALL"
    title = f"{stall_label} SALES"
    subtitle = target_date.strftime("%A, %B %d, %Y")

    # Different headers for Main vs Sub stall
    if stall.stall_type == "main":
        sales_header_end = "I4"
        sales_headers = ["Quantity", "Description", "Amount", "Client Name", "Book #", "Receipt #", "Service Type", "Technicians", "Payment Method"]
        sales_data_cols = 9
        summary_start_col_idx = 12  # Column L to avoid overlap with sales panel
    else:
        sales_header_end = "G4"
        sales_headers = ["Quantity", "Description", "Amount", "Client Name", "Book #", "Receipt #", "Payment Method"]
        sales_data_cols = 7
        summary_start_col_idx = 10  # Column J

    def _col_letter(col_idx_1_based: int) -> str:
        letter = ""
        while col_idx_1_based > 0:
            col_idx_1_based, rem = divmod(col_idx_1_based - 1, 26)
            letter = chr(65 + rem) + letter
        return letter

    summary_start_col = _col_letter(summary_start_col_idx)
    remittance_end_col = _col_letter(summary_start_col_idx + 1)
    summary_values_col = _col_letter(summary_start_col_idx + 1)
    cash_end_col = _col_letter(summary_start_col_idx + 3)
    expenses_end_col = _col_letter(summary_start_col_idx + 3)

    blocks: list[dict[str, Any]] = [
        {"a1": f"A1:{chr(64 + sales_data_cols)}1", "values": [[title]]},
        {"a1": f"A2:{chr(64 + sales_data_cols)}2", "values": [[subtitle]]},
        {
            "a1": f"A4:{sales_header_end}",
            "values": [sales_headers],
        },
        {"a1": f"{summary_start_col}1:{remittance_end_col}1", "values": [["REMITTANCES SUMMARY", ""]]},
        {
            "a1": f"{summary_start_col}2:{summary_values_col}13",
            "values": [
                ["Total Cash Sales", _serialize_decimal(metrics["total_cash_sales"])],
                ["Total GCash Sales", _serialize_decimal(metrics["total_gcash_sales"])],
                ["Total Credit Sales", _serialize_decimal(metrics["total_credit_sales"])],
                ["Total Debit Sales", _serialize_decimal(metrics["total_debit_sales"])],
                ["Total Cheque Sales", _serialize_decimal(metrics["total_cheque_sales"])],
                ["Total Expenses", _serialize_decimal(metrics["total_expenses"])],
                ["COD (Prev Day)", _serialize_decimal(metrics["cod_for_today"])],
                ["COD (Next Day)", _serialize_decimal(metrics["cod_for_next_day"])],
                ["Expected Remittance", _serialize_decimal(metrics["expected_remittance"])],
                ["Remitted Amount", _serialize_decimal(metrics["remitted_amount"])],
                ["Declared Amount", _serialize_decimal(metrics["declared_amount"])],
                ["Over / Short", _serialize_decimal(metrics["balance"])],
            ],
        },
        {"a1": f"{summary_start_col}15:{cash_end_col}15", "values": [["CASH / COINS BREAKDOWN", "", "", ""]]},
        {"a1": f"{summary_start_col}16:{cash_end_col}16", "values": [["Denomination", "Remitted", "Declared", "COD"]]},
        {"a1": f"{summary_start_col}27:{expenses_end_col}27", "values": [["EXPENSES", "", "", ""]]},
        {"a1": f"{summary_start_col}28:{expenses_end_col}28", "values": [["Category", "Vendor", "Description", "Amount"]]},
    ]

    if sales_rows:
        sales_end_col = chr(64 + sales_data_cols)
        blocks.append({
            "a1": f"A5:{sales_end_col}{4 + len(sales_rows)}",
            "values": sales_rows,
        })

    denom_rows = metrics["denominations"] or [["1000", "0", "0", "0"], ["500", "0", "0", "0"], ["200", "0", "0", "0"], ["100", "0", "0", "0"], ["50", "0", "0", "0"], ["20", "0", "0", "0"], ["10", "0", "0", "0"], ["5", "0", "0", "0"], ["1", "0", "0", "0"]]
    blocks.append({
        "a1": f"{summary_start_col}17:{cash_end_col}{16 + len(denom_rows)}",
        "values": denom_rows,
    })

    if expense_rows:
        blocks.append({
            "a1": f"{summary_start_col}29:{expenses_end_col}{28 + len(expense_rows)}",
            "values": expense_rows,
        })

    _write_blocks(sheet_api, spreadsheet_id, tab_name, blocks)

    _style_day_tab(
        service,
        spreadsheet_id,
        tab_name,
        sales_rows_count=len(sales_rows),
        expense_rows_count=len(expense_rows),
        stall_type=stall.stall_type,
        over_short_value=metrics["balance"],
    )

    # Navigate to the latest daily tab on open
    _navigate_to_latest_daily_tab(service, spreadsheet_id, target_date)


def _navigate_to_latest_daily_tab(service, spreadsheet_id: str, target_date: date | None = None):
    """Set today's daily tab as the active sheet when available."""
    try:
        target_date = target_date or timezone.localdate()
        metadata = _execute_with_backoff(
            service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                fields="sheets(properties(sheetId,title,index))"
            ),
            operation="spreadsheets.get sheets for navigation",
        )

        current_gid = _current_daily_tab_gid(metadata.get("sheets", []), target_date)
        if current_gid is not None:
            # Update the active sheet to today's tab when it exists.
            _execute_with_backoff(
                service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={
                        "requests": [
                            {
                                "updateSheetProperties": {
                                    "properties": {
                                        "sheetId": current_gid,
                                        "index": len(metadata.get("sheets", [])) - 1,
                                    },
                                    "fields": "index",
                                }
                            }
                        ]
                    },
                ),
                operation="spreadsheets.batchUpdate set active sheet",
            )
    except Exception as exc:
        logger.debug("Failed to navigate to latest daily tab: %s", exc)


def _get_monthly_sheet_latest_gid(spreadsheet_id: str, sync_config: dict) -> int | None:
    """Get the latest daily tab GID for a monthly sheet."""
    if not spreadsheet_id:
        return None

    service, _, init_error = _get_sheets_clients(sync_config, spreadsheet_id)
    if service is None:
        return None

    try:
        sheet_meta = _execute_with_backoff(
            service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                fields="sheets(properties(sheetId,title,index))",
            ),
            operation=f"get monthly sheet metadata {spreadsheet_id}",
        )
        return _latest_daily_tab_gid(sheet_meta.get("sheets", []))
    except Exception as exc:
        logger.debug("Failed to get latest GID for monthly sheet %s: %s", spreadsheet_id, exc)
        return None


def _get_monthly_sheet_current_gid(spreadsheet_id: str, sync_config: dict) -> int | None:
    """Get today's daily tab GID for a monthly sheet."""
    if not spreadsheet_id:
        return None

    service, _, init_error = _get_sheets_clients(sync_config, spreadsheet_id)
    if service is None:
        return None

    try:
        sheet_meta = _execute_with_backoff(
            service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                fields="sheets(properties(sheetId,title,index))",
            ),
            operation=f"get monthly sheet metadata {spreadsheet_id}",
        )
        current_gid = _current_daily_tab_gid(sheet_meta.get("sheets", []), timezone.localdate())
        if current_gid is not None:
            return current_gid
        return _latest_daily_tab_gid(sheet_meta.get("sheets", []))
    except Exception as exc:
        logger.debug("Failed to get current GID for monthly sheet %s: %s", spreadsheet_id, exc)
        return None


def get_google_sheets_sync_status() -> dict[str, Any]:
    sync_config = _get_google_sync_config()
    raw_json = (sync_config.get("service_account_json") or "").strip()
    json_path = (sync_config.get("service_account_file") or "").strip()
    share_email = (sync_config.get("share_email") or "").strip()

    status: dict[str, Any] = {
        "enabled": bool(sync_config.get("enabled")),
        "sub_spreadsheet_id": sync_config.get("sub_spreadsheet_id", ""),
        "main_spreadsheet_id": sync_config.get("main_spreadsheet_id", ""),
        "sync_scope": sync_config.get("sync_scope", "sub"),
        "share_email": share_email,
        "share_email_configured": bool(share_email),
        "credential_configured": bool(raw_json or json_path),
        "connection_ok": False,
        "sub_current_gid": None,
        "sub_latest_gid": None,
        "main_current_gid": None,
        "main_latest_gid": None,
        "monthly_links_count": StallMonthlySheet.objects.filter(is_active=True).count(),
        "current_month_sheets": {},
        "message": "",
    }

    if raw_json:
        try:
            json.loads(raw_json)
        except Exception as exc:
            status["message"] = f"Service account JSON is invalid: {exc}"
            return status

    # Get current month's sheets
    current_month_key = _month_key_for_date(timezone.localdate())
    monthly_sheets = StallMonthlySheet.objects.filter(
        month_key=current_month_key,
        is_active=True,
    ).select_related("stall")

    for monthly_sheet in monthly_sheets:
        current_gid = _get_monthly_sheet_current_gid(monthly_sheet.spreadsheet_id, sync_config)
        latest_gid = _get_monthly_sheet_latest_gid(monthly_sheet.spreadsheet_id, sync_config)
        status["current_month_sheets"][monthly_sheet.stall.stall_type] = {
            "spreadsheet_id": monthly_sheet.spreadsheet_id,
            "current_gid": current_gid,
            "latest_gid": latest_gid,
            "stall_name": monthly_sheet.stall.name,
        }

    checks = []
    details: dict[str, Any] = {}

    for stall_type in _scope_stall_types(sync_config.get("sync_scope", "sub")):
        spreadsheet_id = _spreadsheet_id_for_stall(sync_config, stall_type)

        if not spreadsheet_id:
            checks.append(f"{stall_type}: Not configured")
            details[stall_type] = {"status": "not_configured", "message": "Spreadsheet ID not configured"}
            continue

        # First verify service account has access
        has_access, access_error = _verify_service_account_access(sync_config, spreadsheet_id)
        if not has_access:
            checks.append(f"{stall_type}: No access - {access_error}")
            details[stall_type] = {"status": "no_access", "message": access_error}
            continue

        service, sheet_api, init_error = _get_sheets_clients(sync_config, spreadsheet_id)
        if service is None or sheet_api is None:
            checks.append(f"{stall_type}: Connection failed - {init_error}")
            details[stall_type] = {"status": "connection_failed", "message": init_error}
            continue

        try:
            # Read-only connection check to avoid consuming write quota during status checks.
            sheet_meta = _execute_with_backoff(
                service.spreadsheets().get(
                    spreadsheetId=spreadsheet_id,
                    fields="spreadsheetId,properties.title,sheets(properties(sheetId,title,index))",
                ),
                operation=f"status check {stall_type}",
            )
            current_gid = _current_daily_tab_gid(sheet_meta.get("sheets", []), timezone.localdate())
            latest_gid = _latest_daily_tab_gid(sheet_meta.get("sheets", []))
            if stall_type == "sub":
                status["sub_current_gid"] = current_gid
                status["sub_latest_gid"] = latest_gid
            elif stall_type == "main":
                status["main_current_gid"] = current_gid
                status["main_latest_gid"] = latest_gid

            sheet_title = sheet_meta.get("properties", {}).get("title", "Unknown")
            checks.append(f"{stall_type}: Connected")
            details[stall_type] = {"status": "connected", "message": f"Connected to \"{sheet_title}\""}
        except Exception as exc:
            logger.exception("Google Sheets status check failed for %s: %s", stall_type, exc)
            error_msg = _normalize_google_error_text(str(exc))
            checks.append(f"{stall_type}: {error_msg}")
            details[stall_type] = {"status": "error", "message": error_msg}

    status["connection_ok"] = all(d.get("status") == "connected" for d in details.values() if d.get("status") != "not_configured")
    status["connection_details"] = details
    status["message"] = " | ".join(checks) if checks else "No scope selected"
    return status


def sync_sales_day_to_google_sheet(stall_id: int, target_date: date) -> bool:
    ok, _ = _sync_sales_day_to_google_sheet_result(stall_id, target_date)
    return ok


def _sync_sales_day_to_google_sheet_result(stall_id: int, target_date: date) -> tuple[bool, str]:
    sync_config = _get_google_sync_config()
    if not sync_config.get("enabled"):
        return False, "Google Sheets sync is disabled"

    try:
        stall = Stall.objects.get(pk=stall_id)
    except Stall.DoesNotExist:
        logger.warning("Google Sheets day sync skipped: stall %s does not exist", stall_id)
        return False, f"Stall {stall_id} does not exist"

    spreadsheet_id, monthly_sheet = _resolve_spreadsheet_target(sync_config, stall, target_date)
    service, sheet_api, init_error = _get_sheets_clients(sync_config, spreadsheet_id)
    if service is None or sheet_api is None:
        logger.warning("Google Sheets day sync skipped: %s", init_error)
        return False, init_error

    tab_name = _daily_tab_name(target_date)
    lock_key = _acquire_day_sync_lock(spreadsheet_id, tab_name)
    if lock_key is None:
        logger.info(
            "Google Sheets day sync skipped for spreadsheet=%s tab=%s because another sync is already in progress",
            spreadsheet_id,
            tab_name,
        )
        return True, "Google Sheets sync already in progress"

    try:
        _render_day_tab(service, sheet_api, spreadsheet_id, stall, target_date)

        share_email = (sync_config.get("share_email") or "").strip()
        if monthly_sheet and share_email and (
            not monthly_sheet.shared_ok or monthly_sheet.shared_to_email != share_email
        ):
            shared_ok, share_error = _share_sheet_with_email(sync_config, spreadsheet_id, share_email)
            monthly_sheet.shared_ok = shared_ok
            monthly_sheet.shared_to_email = share_email if shared_ok else ""
            monthly_sheet.shared_at = timezone.now() if shared_ok else None
            monthly_sheet.share_error = "" if shared_ok else (share_error or "Unknown share error")
            monthly_sheet.save(
                update_fields=[
                    "shared_ok",
                    "shared_to_email",
                    "shared_at",
                    "share_error",
                    "updated_at",
                ]
            )

        return True, ""
    except Exception as exc:
        logger.exception(
            "Google Sheets day sync failed for stall=%s date=%s: %s",
            stall_id,
            target_date,
            exc,
        )
        return False, str(exc)
    finally:
        _release_day_sync_lock(lock_key)


def sync_historical_sales_to_google_sheets(
    limit: int | None = None,
    start_date=None,
    end_date=None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
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
    stalls = list(Stall.objects.filter(stall_type__in=stall_types, is_deleted=False))

    day_targets_by_stall: dict[int, set[date]] = {stall.id: set() for stall in stalls}

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
        day_targets_by_stall.setdefault(tx.stall_id, set()).add(tx.effective_date)

    payment_qs = SalesPayment.objects.filter(
        transaction__stall__in=stalls,
        transaction__voided=False,
        transaction__is_deleted=False,
    ).select_related("transaction")
    if start_date:
        payment_qs = payment_qs.filter(payment_date__date__gte=start_date)
    if end_date:
        payment_qs = payment_qs.filter(payment_date__date__lte=end_date)
    for payment in payment_qs:
        if payment.payment_date:
            day_targets_by_stall.setdefault(payment.transaction.stall_id, set()).add(
                payment.payment_date.date()
            )

    remit_qs = RemittanceRecord.objects.filter(stall__in=stalls)
    if start_date:
        remit_qs = remit_qs.filter(remittance_date__gte=start_date)
    if end_date:
        remit_qs = remit_qs.filter(remittance_date__lte=end_date)
    for rem in remit_qs:
        if rem.remittance_date:
            day_targets_by_stall.setdefault(rem.stall_id, set()).add(rem.remittance_date)

    exp_qs = Expense.objects.filter(stall__in=stalls, is_deleted=False)
    if start_date:
        exp_qs = exp_qs.filter(expense_date__gte=start_date)
    if end_date:
        exp_qs = exp_qs.filter(expense_date__lte=end_date)
    for expense in exp_qs:
        if expense.expense_date:
            day_targets_by_stall.setdefault(expense.stall_id, set()).add(expense.expense_date)

    if start_date and end_date:
        for stall_id in day_targets_by_stall:
            for target_date in _inclusive_date_range(start_date, end_date):
                day_targets_by_stall[stall_id].add(target_date)
    else:
        for stall_id, dates in day_targets_by_stall.items():
            if not dates:
                continue
            min_date = min(dates)
            max_date = max(dates)
            for target_date in _inclusive_date_range(min_date, max_date):
                dates.add(target_date)

    ordered_targets = sorted(
        {
            (stall_id, target_date)
            for stall_id, dates in day_targets_by_stall.items()
            for target_date in dates
        },
        key=lambda x: (x[0], x[1]),
    )
    if isinstance(limit, int) and limit > 0:
        ordered_targets = ordered_targets[:limit]

    total_targets = len(ordered_targets)

    synced = 0
    failed = 0
    errors: list[str] = []
    latest_error = ""

    if progress_callback:
        progress_callback(
            {
                "state": "running",
                "total_targets": total_targets,
                "processed_targets": 0,
                "synced": 0,
                "failed": 0,
                "progress_pct": 0,
                "message": "Historical sync is running",
                    "latest_error": "",
            }
        )

    for index, (stall_id, target_date) in enumerate(ordered_targets, start=1):
        ok, error_detail = _sync_sales_day_to_google_sheet_result(stall_id, target_date)
        if ok:
            synced += 1
        else:
            failed += 1
            if error_detail:
                errors.append(f"stall={stall_id}, date={target_date}: {error_detail}")
                latest_error = str(error_detail)
            else:
                errors.append(f"stall={stall_id}, date={target_date}")
                latest_error = f"stall={stall_id}, date={target_date}"

        if progress_callback:
            progress_callback(
                {
                    "state": "running",
                    "total_targets": total_targets,
                    "processed_targets": index,
                    "synced": synced,
                    "failed": failed,
                    "current_stall_id": stall_id,
                    "current_date": str(target_date),
                    "progress_pct": int((index * 100) / total_targets) if total_targets > 0 else 100,
                    "message": "Historical sync is running",
                    "latest_error": latest_error,
                }
            )

    return {
        "ok": failed == 0,
        "message": "Historical sync completed" if failed == 0 else "Historical sync completed with errors",
        "synced": synced,
        "failed": failed,
        "considered": synced + failed,
        "total_targets": total_targets,
        "processed_targets": synced + failed,
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

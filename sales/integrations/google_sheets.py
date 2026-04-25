import importlib
import json
import logging
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable

from django.conf import settings
from django.db.models import Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from expenses.models import Expense
from inventory.models import Stall
from remittances.models import RemittanceRecord
from sales.models import PaymentStatus, SalesPayment, SalesTransaction

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


def _parse_daily_tab_date(title: str, today: date) -> date | None:
    """Parse tab titles like 'APRIL 22' into a comparable date near today."""
    raw = (title or "").strip()
    if not raw:
        return None

    try:
        parsed = datetime.strptime(raw.title(), "%B %d").date().replace(year=today.year)
    except Exception:
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


def _style_day_tab(service, spreadsheet_id: str, tab_name: str, sales_rows_count: int, stall_type: str = "sub"):
    metadata = _execute_with_backoff(
        service.spreadsheets().get(spreadsheetId=spreadsheet_id),
        operation="spreadsheets.get style metadata",
    )
    sheet_id = None
    for sheet in metadata.get("sheets", []):
        props = sheet.get("properties", {})
        if props.get("title") == tab_name:
            sheet_id = props.get("sheetId")
            break

    if sheet_id is None:
        return

    sales_end_row = max(4, 4 + sales_rows_count)
    sales_data_cols = 9 if stall_type == "main" else 7
    
    requests = []
    
    # Set column widths
    # Column B (Description) = 240
    # Column D (Client Name) = 200
    # Column J (Labels) = 160
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
                    "startIndex": 9,  # Column J
                    "endIndex": 10,
                },
                "properties": {"pixelSize": 160},
                "fields": "pixelSize",
            }
        },
    ])
    
    # Unmerge cells first
    requests.extend([
        {
            "unmergeCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 2,
                    "startColumnIndex": 0,
                    "endColumnIndex": sales_data_cols,
                }
            }
        },
        {
            "unmergeCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 9,
                    "endColumnIndex": 13,
                }
            }
        },
        {
            "unmergeCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 14,
                    "endRowIndex": 15,
                    "startColumnIndex": 9,
                    "endColumnIndex": 13,
                }
            }
        },
        {
            "unmergeCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 26,
                    "endRowIndex": 27,
                    "startColumnIndex": 9,
                    "endColumnIndex": 12,
                }
            }
        },
    ])
    
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
                    "startColumnIndex": 9,
                    "endColumnIndex": 13,
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
                    "startColumnIndex": 9,
                    "endColumnIndex": 13,
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
                    "startColumnIndex": 9,
                    "endColumnIndex": 12,
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
    
    # REMITTANCES SUMMARY header (row 1, cols J-M)
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": 1,
                "startColumnIndex": 9,
                "endColumnIndex": 13,
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
    
    # Remittance metrics rows (rows 2-13, cols J-K) - bold labels + borders
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,
                "endRowIndex": 13,
                "startColumnIndex": 9,
                "endColumnIndex": 11,
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
    
    # Remittance values (rows 2-13, cols L-M) - right aligned + borders
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,
                "endRowIndex": 13,
                "startColumnIndex": 10,
                "endColumnIndex": 13,
            },
            "cell": {
                "userEnteredFormat": {
                    "horizontalAlignment": "RIGHT",
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
    
    # CASH / COINS BREAKDOWN header (row 15, cols J-M)
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 14,
                "endRowIndex": 15,
                "startColumnIndex": 9,
                "endColumnIndex": 13,
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
    
    # Denominations header row (row 16, cols J-M) - bold labels + borders
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 15,
                "endRowIndex": 16,
                "startColumnIndex": 9,
                "endColumnIndex": 13,
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
    
    # Denominations data rows (rows 17-25, cols J-M) - RED denomination labels + borders
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 16,
                "endRowIndex": 25,
                "startColumnIndex": 9,
                "endColumnIndex": 13,
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
                "startColumnIndex": 9,
                "endColumnIndex": 10,
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
                "startColumnIndex": 9,
                "endColumnIndex": 12,
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
                "startColumnIndex": 9,
                "endColumnIndex": 12,
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
        .filter(effective_date=target_date)
        .order_by("manual_receipt_number", "id")
    )

    sales_rows = _build_sales_rows(transactions, stall.stall_type)
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
    else:
        sales_header_end = "G4"
        sales_headers = ["Quantity", "Description", "Amount", "Client Name", "Book #", "Receipt #", "Payment Method"]
        sales_data_cols = 7

    blocks: list[dict[str, Any]] = [
        {"a1": f"A1:{chr(64 + sales_data_cols)}1", "values": [[title]]},
        {"a1": f"A2:{chr(64 + sales_data_cols)}2", "values": [[subtitle]]},
        {
            "a1": f"A4:{sales_header_end}",
            "values": [sales_headers],
        },
        {"a1": "J1:M1", "values": [["REMITTANCES SUMMARY", "", "", ""]]},
        {
            "a1": "J2:K13",
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
        {"a1": "J15:M15", "values": [["CASH / COINS BREAKDOWN", "", "", ""]]},
        {"a1": "J16:M16", "values": [["Denomination", "Remitted", "Declared", "COD"]]},
        {"a1": "J27:L27", "values": [["EXPENSES", "", ""]]},
        {"a1": "J28:L28", "values": [["Type", "Description", "Amount"]]},
    ]

    if sales_rows:
        sales_end_col = chr(64 + sales_data_cols)
        blocks.append({
            "a1": f"A5:{sales_end_col}{4 + len(sales_rows)}",
            "values": sales_rows,
        })

    denom_rows = metrics["denominations"] or [["1000", "0", "0", "0"], ["500", "0", "0", "0"], ["200", "0", "0", "0"], ["100", "0", "0", "0"], ["50", "0", "0", "0"], ["20", "0", "0", "0"], ["10", "0", "0", "0"], ["5", "0", "0", "0"], ["1", "0", "0", "0"]]
    blocks.append({
        "a1": f"J17:M{16 + len(denom_rows)}",
        "values": denom_rows,
    })

    if expense_rows:
        blocks.append({
            "a1": f"J29:L{28 + len(expense_rows)}",
            "values": expense_rows,
        })

    _write_blocks(sheet_api, spreadsheet_id, tab_name, blocks)

    _style_day_tab(
        service,
        spreadsheet_id,
        tab_name,
        sales_rows_count=len(sales_rows),
        stall_type=stall.stall_type,
    )
    
    # Navigate to the latest daily tab on open
    _navigate_to_latest_daily_tab(service, spreadsheet_id)


def _navigate_to_latest_daily_tab(service, spreadsheet_id: str):
    """Set the latest daily tab as the active sheet."""
    try:
        metadata = _execute_with_backoff(
            service.spreadsheets().get(
                spreadsheetId=spreadsheet_id,
                fields="sheets(properties(sheetId,title,index))"
            ),
            operation="spreadsheets.get sheets for navigation",
        )
        
        latest_gid = _latest_daily_tab_gid(metadata.get("sheets", []))
        if latest_gid is not None:
            # Update the active sheet to the latest daily tab
            _execute_with_backoff(
                service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={
                        "requests": [
                            {
                                "updateSheetProperties": {
                                    "properties": {
                                        "sheetId": latest_gid,
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
        "sub_latest_gid": None,
        "main_latest_gid": None,
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
            # Read-only connection check to avoid consuming write quota during status checks.
            sheet_meta = _execute_with_backoff(
                service.spreadsheets().get(
                    spreadsheetId=spreadsheet_id,
                    fields="spreadsheetId,properties.title,sheets(properties(sheetId,title,index))",
                ),
                operation=f"status check {stall_type}",
            )
            latest_gid = _latest_daily_tab_gid(sheet_meta.get("sheets", []))
            if stall_type == "sub":
                status["sub_latest_gid"] = latest_gid
            elif stall_type == "main":
                status["main_latest_gid"] = latest_gid
            checks.append(f"{stall_type}: ok")
        except Exception as exc:
            logger.exception("Google Sheets status check failed for %s: %s", stall_type, exc)
            checks.append(f"{stall_type}: {exc}")

    status["connection_ok"] = all(c.endswith("ok") for c in checks)
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

    spreadsheet_id = _spreadsheet_id_for_stall(sync_config, stall.stall_type)
    service, sheet_api, init_error = _get_sheets_clients(sync_config, spreadsheet_id)
    if service is None or sheet_api is None:
        logger.warning("Google Sheets day sync skipped: %s", init_error)
        return False, init_error

    try:
        _render_day_tab(service, sheet_api, spreadsheet_id, stall, target_date)
        return True, ""
    except Exception as exc:
        logger.exception(
            "Google Sheets day sync failed for stall=%s date=%s: %s",
            stall_id,
            target_date,
            exc,
        )
        return False, str(exc)


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

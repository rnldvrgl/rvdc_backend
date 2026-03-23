"""
Centralized export views for Sales and Cheque Collections reports.
Generates multi-sheet Excel exports with openpyxl.
"""
from collections import defaultdict
from decimal import Decimal
from io import BytesIO

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce, TruncDate, TruncMonth
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from rest_framework import status as drf_status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView


# ── Shared styling ─────────────────────────────────────────────────
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
HEADER_FILL = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
GREEN_FILL = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
RED_FILL = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
AMBER_FILL = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
BLUE_FILL = PatternFill(start_color="DBEAFE", end_color="DBEAFE", fill_type="solid")
THIN_BORDER = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"), bottom=Side(style="thin"),
)


def _style_header(ws, col_count, row=1):
    for col in range(1, col_count + 1):
        cell = ws.cell(row=row, column=col)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = THIN_BORDER


def _auto_width(ws):
    for col_cells in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col_cells[0].column)
        for cell in col_cells:
            if cell.value is not None:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = min(max_len + 3, 50)


def _write_rows(ws, headers, rows, start_row=1):
    for col_idx, header in enumerate(headers, 1):
        ws.cell(row=start_row, column=col_idx, value=header)
    _style_header(ws, len(headers), start_row)
    for row_idx, row_data in enumerate(rows, start_row + 1):
        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.border = THIN_BORDER
            cell.alignment = Alignment(vertical="center")
    _auto_width(ws)
    return start_row + len(rows)


def _parse_date(val, default=None):
    """Parse a date string (YYYY-MM-DD) into a date object."""
    from datetime import datetime
    if not val:
        return default
    try:
        return datetime.strptime(val, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return default


def _workbook_response(wb, prefix):
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    timestamp = timezone.now().strftime("%Y%m%d_%H%M")
    filename = f"{prefix}_{timestamp}.xlsx"
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# ═══════════════════════════════════════════════════════════════════
#  SALES EXPORT
# ═══════════════════════════════════════════════════════════════════

class SalesExportView(APIView):
    """
    Generate Excel sales report.

    GET /api/sales/export-report/
    Query params:
        start_date  — YYYY-MM-DD (default: 30 days ago)
        end_date    — YYYY-MM-DD (default: today)
        sheets      — comma-separated: all_transactions, daily_summary,
                       monthly_summary, quarterly_summary, payment_breakdown,
                       top_items (default: all)
    """
    permission_classes = [IsAdminUser]

    VALID_SHEETS = {
        "all_transactions", "daily_summary", "monthly_summary",
        "quarterly_summary", "payment_breakdown", "top_items",
    }

    def get(self, request):
        from datetime import timedelta
        today = timezone.now().date()
        start = _parse_date(request.query_params.get("start_date"), today - timedelta(days=30))
        end = _parse_date(request.query_params.get("end_date"), today)

        sheets_param = request.query_params.get("sheets", "")
        if sheets_param:
            requested = [s.strip() for s in sheets_param.split(",") if s.strip()]
            invalid = [s for s in requested if s not in self.VALID_SHEETS]
            if invalid:
                return Response(
                    {"detail": f"Invalid sheet(s): {', '.join(invalid)}"},
                    status=drf_status.HTTP_400_BAD_REQUEST,
                )
        else:
            requested = list(self.VALID_SHEETS)

        from sales.models import SalesTransaction, SalesItem, SalesPayment

        # Base queryset
        txns = (
            SalesTransaction.objects.filter(
                is_deleted=False, voided=False,
                created_at__date__gte=start,
                created_at__date__lte=end,
            )
            .select_related("stall", "client", "sales_clerk")
            .prefetch_related("items__item", "payments")
            .order_by("created_at")
        )

        wb = Workbook()
        # Summary sheet
        ws = wb.active
        ws.title = "Summary"
        ws.cell(row=1, column=1, value="RVDC Sales Report").font = Font(bold=True, size=16, color="2563EB")
        ws.cell(row=2, column=1, value=f"Period: {start.strftime('%b %d, %Y')} — {end.strftime('%b %d, %Y')}")
        ws.cell(row=2, column=1).font = Font(italic=True, color="666666")
        ws.cell(row=3, column=1, value=f"Generated: {timezone.now().strftime('%B %d, %Y %I:%M %p')}")
        ws.cell(row=3, column=1).font = Font(italic=True, color="666666")

        total_count = txns.count()
        total_sales = sum(float(t.computed_total) for t in txns)
        total_paid = sum(float(t.total_paid) for t in txns)

        stats = [
            ("Total Transactions", total_count),
            ("Total Sales", f"₱{total_sales:,.2f}"),
            ("Total Collected", f"₱{total_paid:,.2f}"),
            ("Outstanding Balance", f"₱{max(total_sales - total_paid, 0):,.2f}"),
        ]
        row = 5
        ws.cell(row=row, column=1, value="Metric").font = HEADER_FONT
        ws.cell(row=row, column=1).fill = HEADER_FILL
        ws.cell(row=row, column=1).border = THIN_BORDER
        ws.cell(row=row, column=2, value="Value").font = HEADER_FONT
        ws.cell(row=row, column=2).fill = HEADER_FILL
        ws.cell(row=row, column=2).border = THIN_BORDER
        for label, value in stats:
            row += 1
            ws.cell(row=row, column=1, value=label).border = THIN_BORDER
            c = ws.cell(row=row, column=2, value=value)
            c.border = THIN_BORDER
        ws.column_dimensions["A"].width = 30
        ws.column_dimensions["B"].width = 25

        # All Transactions sheet
        if "all_transactions" in requested:
            ws_t = wb.create_sheet("All Transactions")
            headers = [
                "ID", "Date", "Client", "Stall", "Clerk", "Type",
                "Items", "Subtotal", "Discount", "Total",
                "Paid", "Balance", "Status",
            ]
            rows_data = []
            for t in txns:
                subtotal = float(t.subtotal)
                total = float(t.computed_total)
                paid = float(t.total_paid)
                rows_data.append([
                    t.id,
                    t.created_at.strftime("%Y-%m-%d %I:%M %p"),
                    t.client.full_name if t.client else "Walk-in",
                    t.stall.name if t.stall else "—",
                    t.sales_clerk.get_full_name() if t.sales_clerk else "—",
                    t.get_transaction_type_display(),
                    t.total_items,
                    subtotal, float(t.order_discount or 0),
                    total, paid, max(total - paid, 0),
                    t.get_payment_status_display(),
                ])
            last = _write_rows(ws_t, headers, rows_data)
            # Color-code status
            stat_col = headers.index("Status") + 1
            for ri in range(2, last + 1):
                cell = ws_t.cell(row=ri, column=stat_col)
                if cell.value == "Paid":
                    for c in range(1, len(headers) + 1):
                        ws_t.cell(row=ri, column=c).fill = GREEN_FILL
                elif cell.value == "Unpaid":
                    for c in range(1, len(headers) + 1):
                        ws_t.cell(row=ri, column=c).fill = RED_FILL
                elif cell.value == "Partial":
                    for c in range(1, len(headers) + 1):
                        ws_t.cell(row=ri, column=c).fill = AMBER_FILL

        # Daily Summary
        if "daily_summary" in requested:
            ws_d = wb.create_sheet("Daily Summary")
            daily = (
                txns.annotate(day=TruncDate("created_at"))
                .values("day")
                .annotate(
                    count=Count("id"),
                    total=Coalesce(Sum("change_amount"), Decimal("0")),
                )
                .order_by("day")
            )
            # Re-compute from actual transaction data for accuracy
            daily_map = defaultdict(lambda: {"count": 0, "total": Decimal("0"), "paid": Decimal("0")})
            for t in txns:
                day = t.created_at.date()
                daily_map[day]["count"] += 1
                daily_map[day]["total"] += t.computed_total
                daily_map[day]["paid"] += t.total_paid

            headers = ["Date", "Transactions", "Total Sales", "Total Collected", "Outstanding"]
            rows_data = []
            for day in sorted(daily_map.keys()):
                d = daily_map[day]
                rows_data.append([
                    day.strftime("%Y-%m-%d"),
                    d["count"],
                    float(d["total"]),
                    float(d["paid"]),
                    float(max(d["total"] - d["paid"], 0)),
                ])
            _write_rows(ws_d, headers, rows_data)

        # Monthly Summary
        if "monthly_summary" in requested:
            ws_m = wb.create_sheet("Monthly Summary")
            monthly_map = defaultdict(lambda: {"count": 0, "total": Decimal("0"), "paid": Decimal("0")})
            for t in txns:
                key = t.created_at.strftime("%Y-%m")
                monthly_map[key]["count"] += 1
                monthly_map[key]["total"] += t.computed_total
                monthly_map[key]["paid"] += t.total_paid

            headers = ["Month", "Transactions", "Total Sales", "Total Collected", "Outstanding"]
            rows_data = []
            for month in sorted(monthly_map.keys()):
                d = monthly_map[month]
                rows_data.append([
                    month, d["count"], float(d["total"]),
                    float(d["paid"]), float(max(d["total"] - d["paid"], 0)),
                ])
            _write_rows(ws_m, headers, rows_data)

        # Quarterly Summary
        if "quarterly_summary" in requested:
            ws_q = wb.create_sheet("Quarterly Summary")
            quarterly_map = defaultdict(lambda: {"count": 0, "total": Decimal("0"), "paid": Decimal("0")})
            for t in txns:
                q = (t.created_at.month - 1) // 3 + 1
                key = f"{t.created_at.year} Q{q}"
                quarterly_map[key]["count"] += 1
                quarterly_map[key]["total"] += t.computed_total
                quarterly_map[key]["paid"] += t.total_paid

            headers = ["Quarter", "Transactions", "Total Sales", "Total Collected", "Outstanding"]
            rows_data = []
            for quarter in sorted(quarterly_map.keys()):
                d = quarterly_map[quarter]
                rows_data.append([
                    quarter, d["count"], float(d["total"]),
                    float(d["paid"]), float(max(d["total"] - d["paid"], 0)),
                ])
            _write_rows(ws_q, headers, rows_data)

        # Payment Breakdown
        if "payment_breakdown" in requested:
            ws_p = wb.create_sheet("Payment Breakdown")
            payment_map = defaultdict(lambda: {"count": 0, "amount": Decimal("0")})
            for t in txns:
                for p in t.payments.all():
                    payment_map[p.get_payment_type_display()]["count"] += 1
                    payment_map[p.get_payment_type_display()]["amount"] += p.amount

            headers = ["Payment Type", "Count", "Total Amount"]
            rows_data = []
            for ptype in sorted(payment_map.keys()):
                d = payment_map[ptype]
                rows_data.append([ptype, d["count"], float(d["amount"])])
            _write_rows(ws_p, headers, rows_data)

        # Top Items Sold
        if "top_items" in requested:
            ws_i = wb.create_sheet("Top Items Sold")
            from sales.models import SalesItem
            items_agg = (
                SalesItem.objects.filter(
                    transaction__in=txns,
                    item__isnull=False,
                )
                .values("item__name", "item__sku", "item__category__name")
                .annotate(
                    total_qty=Coalesce(Sum("quantity"), Decimal("0")),
                    total_revenue=Coalesce(Sum("quantity") * Sum("final_price_per_unit") / Count("id"), Decimal("0")),
                )
                .order_by("-total_qty")[:50]
            )
            headers = ["Rank", "Item Name", "SKU", "Category", "Qty Sold", "Revenue"]
            rows_data = []
            for rank, row in enumerate(items_agg, 1):
                # Compute revenue properly from individual records
                item_sales = SalesItem.objects.filter(
                    transaction__in=txns,
                    item__name=row["item__name"],
                    item__isnull=False,
                )
                revenue = sum(float(si.line_total) for si in item_sales)
                rows_data.append([
                    rank,
                    row["item__name"],
                    row["item__sku"] or "—",
                    row["item__category__name"] or "—",
                    float(row["total_qty"]),
                    revenue,
                ])
            _write_rows(ws_i, headers, rows_data)

        return _workbook_response(wb, "sales_report")


# ═══════════════════════════════════════════════════════════════════
#  CHEQUE COLLECTIONS EXPORT
# ═══════════════════════════════════════════════════════════════════

class ChequeExportView(APIView):
    """
    Generate Excel cheque collections report.

    GET /api/receivables/export-report/
    Query params:
        start_date  — YYYY-MM-DD (default: 90 days ago)
        end_date    — YYYY-MM-DD (default: today)
        sheets      — comma-separated: all_cheques, by_status,
                       by_bank, monthly_summary (default: all)
    """
    permission_classes = [IsAdminUser]

    VALID_SHEETS = {"all_cheques", "by_status", "by_bank", "monthly_summary"}

    def get(self, request):
        from datetime import timedelta
        from receivables.models import ChequeCollection

        today = timezone.now().date()
        start = _parse_date(request.query_params.get("start_date"), today - timedelta(days=90))
        end = _parse_date(request.query_params.get("end_date"), today)

        sheets_param = request.query_params.get("sheets", "")
        if sheets_param:
            requested = [s.strip() for s in sheets_param.split(",") if s.strip()]
            invalid = [s for s in requested if s not in self.VALID_SHEETS]
            if invalid:
                return Response(
                    {"detail": f"Invalid sheet(s): {', '.join(invalid)}"},
                    status=drf_status.HTTP_400_BAD_REQUEST,
                )
        else:
            requested = list(self.VALID_SHEETS)

        cheques = (
            ChequeCollection.objects.filter(
                date_collected__date__gte=start,
                date_collected__date__lte=end,
            )
            .select_related("client", "collected_by", "sales_transaction")
            .order_by("date_collected")
        )

        wb = Workbook()
        # Summary
        ws = wb.active
        ws.title = "Summary"
        ws.cell(row=1, column=1, value="RVDC Cheque Collections Report").font = Font(bold=True, size=16, color="2563EB")
        ws.cell(row=2, column=1, value=f"Period: {start.strftime('%b %d, %Y')} — {end.strftime('%b %d, %Y')}")
        ws.cell(row=2, column=1).font = Font(italic=True, color="666666")
        ws.cell(row=3, column=1, value=f"Generated: {timezone.now().strftime('%B %d, %Y %I:%M %p')}")
        ws.cell(row=3, column=1).font = Font(italic=True, color="666666")

        total_count = cheques.count()
        total_billing = sum(float(c.billing_amount) for c in cheques)
        total_cheque = sum(float(c.cheque_amount) for c in cheques)
        pending = cheques.filter(status="pending").count()
        deposited = cheques.filter(status="deposited").count()
        encashed = cheques.filter(status="encashed").count()
        bounced = cheques.filter(status="bounced").count()

        stats = [
            ("Total Cheques", total_count),
            ("Total Billing Amount", f"₱{total_billing:,.2f}"),
            ("Total Cheque Amount", f"₱{total_cheque:,.2f}"),
            ("", ""),
            ("Pending", pending),
            ("Deposited", deposited),
            ("Encashed", encashed),
            ("Bounced", bounced),
        ]
        row = 5
        ws.cell(row=row, column=1, value="Metric").font = HEADER_FONT
        ws.cell(row=row, column=1).fill = HEADER_FILL
        ws.cell(row=row, column=1).border = THIN_BORDER
        ws.cell(row=row, column=2, value="Value").font = HEADER_FONT
        ws.cell(row=row, column=2).fill = HEADER_FILL
        ws.cell(row=row, column=2).border = THIN_BORDER
        for label, value in stats:
            row += 1
            ws.cell(row=row, column=1, value=label).border = THIN_BORDER
            ws.cell(row=row, column=2, value=value).border = THIN_BORDER
            if label == "Bounced" and bounced > 0:
                ws.cell(row=row, column=2).font = Font(bold=True, color="DC2626")
        ws.column_dimensions["A"].width = 30
        ws.column_dimensions["B"].width = 25

        STATUS_FILLS = {
            "pending": AMBER_FILL,
            "deposited": BLUE_FILL,
            "encashed": GREEN_FILL,
            "bounced": RED_FILL,
            "returned": RED_FILL,
            "cancelled": RED_FILL,
        }

        # All Cheques
        if "all_cheques" in requested:
            ws_c = wb.create_sheet("All Cheques")
            headers = [
                "ID", "Date Collected", "Client", "Issued By",
                "Cheque #", "Cheque Date", "Bank", "Deposit Bank",
                "Billing Amount", "Cheque Amount", "OR #",
                "Status", "Collection Type", "Collected By", "Notes",
            ]
            rows_data = []
            for c in cheques:
                rows_data.append([
                    c.id,
                    c.date_collected.strftime("%Y-%m-%d"),
                    c.client.full_name if c.client else "—",
                    c.issued_by or "—",
                    c.cheque_number,
                    c.cheque_date.strftime("%Y-%m-%d") if c.cheque_date else "—",
                    c.get_bank_name_display() if c.bank_name else "—",
                    c.get_deposit_bank_display() if c.deposit_bank else "—",
                    float(c.billing_amount),
                    float(c.cheque_amount),
                    c.or_number or "—",
                    c.get_status_display(),
                    c.get_collection_type_display(),
                    c.collected_by.get_full_name() if c.collected_by else "—",
                    c.notes or "",
                ])
            last = _write_rows(ws_c, headers, rows_data)
            stat_col = headers.index("Status") + 1
            for ri in range(2, last + 1):
                cell = ws_c.cell(row=ri, column=stat_col)
                fill = STATUS_FILLS.get(cell.value.lower() if cell.value else "", None)
                if fill:
                    for ci in range(1, len(headers) + 1):
                        ws_c.cell(row=ri, column=ci).fill = fill

        # By Status
        if "by_status" in requested:
            ws_s = wb.create_sheet("By Status")
            status_agg = defaultdict(lambda: {"count": 0, "billing": Decimal("0"), "cheque": Decimal("0")})
            for c in cheques:
                key = c.get_status_display()
                status_agg[key]["count"] += 1
                status_agg[key]["billing"] += c.billing_amount
                status_agg[key]["cheque"] += c.cheque_amount

            headers = ["Status", "Count", "Total Billing", "Total Cheque Amount"]
            rows_data = []
            for s in sorted(status_agg.keys()):
                d = status_agg[s]
                rows_data.append([s, d["count"], float(d["billing"]), float(d["cheque"])])
            _write_rows(ws_s, headers, rows_data)

        # By Bank
        if "by_bank" in requested:
            ws_b = wb.create_sheet("By Bank")
            bank_agg = defaultdict(lambda: {"count": 0, "amount": Decimal("0")})
            for c in cheques:
                key = c.get_bank_name_display() if c.bank_name else "Unknown"
                bank_agg[key]["count"] += 1
                bank_agg[key]["amount"] += c.cheque_amount

            headers = ["Bank", "Cheques", "Total Amount"]
            rows_data = []
            for bank in sorted(bank_agg.keys()):
                d = bank_agg[bank]
                rows_data.append([bank, d["count"], float(d["amount"])])
            _write_rows(ws_b, headers, rows_data)

        # Monthly Summary
        if "monthly_summary" in requested:
            ws_m = wb.create_sheet("Monthly Summary")
            monthly_map = defaultdict(lambda: {"count": 0, "billing": Decimal("0"), "cheque": Decimal("0")})
            for c in cheques:
                key = c.date_collected.strftime("%Y-%m")
                monthly_map[key]["count"] += 1
                monthly_map[key]["billing"] += c.billing_amount
                monthly_map[key]["cheque"] += c.cheque_amount

            headers = ["Month", "Cheques", "Total Billing", "Total Cheque Amount"]
            rows_data = []
            for month in sorted(monthly_map.keys()):
                d = monthly_map[month]
                rows_data.append([month, d["count"], float(d["billing"]), float(d["cheque"])])
            _write_rows(ws_m, headers, rows_data)

        return _workbook_response(wb, "cheque_report")

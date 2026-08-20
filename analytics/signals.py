from datetime import datetime
import logging

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _date_to_iso(dt):
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.date().isoformat()
    try:
        return dt.isoformat()
    except Exception:
        return None


def _invalidate_for(stall_id=None, date_iso=None):
    try:
        from analytics.cache import invalidate_dashboard_cache

        if stall_id and date_iso:
            # Try to delete keys specific to this date and stall
            pattern = f"dashboard:*{date_iso}*:{stall_id}"
            invalidate_dashboard_cache(prefix=pattern)
            # Also delete keys for this date across all stalls
            pattern_all = f"dashboard:*{date_iso}*:all"
            invalidate_dashboard_cache(prefix=pattern_all)
        elif date_iso:
            pattern = f"dashboard:*{date_iso}*"
            invalidate_dashboard_cache(prefix=pattern)
        elif stall_id:
            pattern = f"dashboard:*:{stall_id}"
            invalidate_dashboard_cache(prefix=pattern)
        else:
            invalidate_dashboard_cache()
    except Exception:
        logger.exception("Failed to invalidate dashboard cache")


# Sales models
@receiver(post_save)
def sales_change_handler(sender, instance, **kwargs):
    name = getattr(sender, "__name__", "")
    try:
        # Only handle relevant models by name to avoid importing heavy modules
        if name in ("SalesTransaction", "SalesPayment"):
            stall = getattr(instance, "stall", None)
            if stall is None and hasattr(instance, "transaction"):
                stall = getattr(instance.transaction, "stall", None)

            # Try to determine an event date
            date_attr = None
            if hasattr(instance, "payment_date"):
                date_attr = instance.payment_date
            elif hasattr(instance, "created_at"):
                date_attr = instance.created_at

            date_iso = _date_to_iso(date_attr)
            stall_id = getattr(stall, "id", None)
            _invalidate_for(stall_id=stall_id, date_iso=date_iso)
    except Exception:
        logger.exception("sales_change_handler failed")


# Service payments and service changes
@receiver(post_save)
def service_change_handler(sender, instance, **kwargs):
    name = getattr(sender, "__name__", "")
    try:
        if name in ("Service", "ServicePayment"):
            stall = getattr(instance, "stall", None)
            # Service may have stall via related fields
            stall_id = getattr(stall, "id", None)
            date_attr = getattr(instance, "created_at", None)
            date_iso = _date_to_iso(date_attr)
            _invalidate_for(stall_id=stall_id, date_iso=date_iso)
    except Exception:
        logger.exception("service_change_handler failed")


# Inventory movements
@receiver(post_save)
def stock_change_handler(sender, instance, **kwargs):
    name = getattr(sender, "__name__", "")
    try:
        if name in ("StockMovement", "Stock"):
            stall = getattr(instance, "stall", None)
            stall_id = getattr(stall, "id", None)
            date_iso = _date_to_iso(getattr(instance, "created_at", None))
            _invalidate_for(stall_id=stall_id, date_iso=date_iso)
    except Exception:
        logger.exception("stock_change_handler failed")


# Remittances
@receiver(post_save)
def remittance_change_handler(sender, instance, **kwargs):
    name = getattr(sender, "__name__", "")
    try:
        if name == "RemittanceRecord":
            stall = getattr(instance, "stall", None)
            stall_id = getattr(stall, "id", None)
            date_iso = _date_to_iso(getattr(instance, "remittance_date", None))
            _invalidate_for(stall_id=stall_id, date_iso=date_iso)
    except Exception:
        logger.exception("remittance_change_handler failed")


# Clients
@receiver(post_save)
def client_change_handler(sender, instance, **kwargs):
    name = getattr(sender, "__name__", "")
    try:
        if name == "Client":
            date_iso = _date_to_iso(getattr(instance, "created_at", None))
            _invalidate_for(date_iso=date_iso)
    except Exception:
        logger.exception("client_change_handler failed")

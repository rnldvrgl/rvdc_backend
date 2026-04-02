from datetime import datetime, timezone as dt_timezone
from typing import Optional
import re

from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from authentication.models import AuthSession
from users.models import CustomUser


def _extract_client_ip(request) -> Optional[str]:
    if not request:
        return None

    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or None

    return request.META.get("REMOTE_ADDR") or None


def _parse_browser(user_agent: str) -> str:
    """Extract browser name + major version from a User-Agent string."""
    ua = user_agent or ""
    # Order matters — specific tokens must be checked before generic ones
    if "Edg/" in ua:
        m = re.search(r"Edg/(\d+)", ua)
        return f"Edge {m.group(1)}" if m else "Edge"
    if "Edge/" in ua:
        m = re.search(r"Edge/(\d+)", ua)
        return f"Edge {m.group(1)}" if m else "Edge"
    if "OPR/" in ua:
        m = re.search(r"OPR/(\d+)", ua)
        return f"Opera {m.group(1)}" if m else "Opera"
    if "SamsungBrowser/" in ua:
        m = re.search(r"SamsungBrowser/([\d.]+)", ua)
        return f"Samsung Browser {m.group(1)}" if m else "Samsung Browser"
    if "Chrome/" in ua:
        m = re.search(r"Chrome/(\d+)", ua)
        return f"Chrome {m.group(1)}" if m else "Chrome"
    if "Firefox/" in ua:
        m = re.search(r"Firefox/(\d+)", ua)
        return f"Firefox {m.group(1)}" if m else "Firefox"
    if "Safari/" in ua:
        m = re.search(r"Version/(\d+)", ua)
        ver = f" {m.group(1)}" if m else ""
        return f"Safari{ver}"
    return "Unknown Browser"


def _parse_os(user_agent: str) -> str:
    """Extract OS name + version from a User-Agent string."""
    ua = user_agent or ""
    if "Windows NT 10.0" in ua:
        return "Windows 10/11"
    if "Windows NT 6.3" in ua:
        return "Windows 8.1"
    if "Windows NT 6.2" in ua:
        return "Windows 8"
    if "Windows NT 6.1" in ua:
        return "Windows 7"
    if "Windows NT 6.0" in ua:
        return "Windows Vista"
    if "Windows" in ua:
        return "Windows"
    if "iPhone" in ua:
        m = re.search(r"CPU iPhone OS ([\d_]+)", ua)
        ver = m.group(1).replace("_", ".") if m else ""
        return f"iOS {ver}" if ver else "iOS"
    if "iPad" in ua:
        m = re.search(r"CPU OS ([\d_]+)", ua)
        ver = m.group(1).replace("_", ".") if m else ""
        return f"iPadOS {ver}" if ver else "iPadOS"
    if "Android" in ua:
        m = re.search(r"Android ([\d.]+)", ua)
        ver = m.group(1) if m else ""
        return f"Android {ver}" if ver else "Android"
    if "Mac OS X" in ua:
        m = re.search(r"Mac OS X ([\d_]+)", ua)
        ver = m.group(1).replace("_", ".") if m else ""
        return f"macOS {ver}" if ver else "macOS"
    if "Linux" in ua:
        return "Linux"
    return "Unknown OS"


def _build_device_label(user_agent: str, explicit_label: str = "") -> str:
    if explicit_label:
        return explicit_label[:255]
    browser = _parse_browser(user_agent)
    os_name = _parse_os(user_agent)
    return f"{browser} on {os_name}"[:255]


def _get_jti_and_exp(refresh_token: str):
    token = RefreshToken(refresh_token)
    jti = str(token.get("jti"))
    exp = token.get("exp")
    expires_at = (
        datetime.fromtimestamp(exp, tz=dt_timezone.utc)
        if isinstance(exp, (int, float))
        else None
    )
    user_id = token.get("user_id")
    return jti, expires_at, user_id


@transaction.atomic
def upsert_login_session(
    user,
    refresh_token: str,
    request,
    device_id: str = "",
    access_jti: str = "",
    remember_me: bool = True,
) -> AuthSession:
    jti, expires_at, _ = _get_jti_and_exp(refresh_token)

    user_agent = request.META.get("HTTP_USER_AGENT", "") if request else ""
    ip_address = _extract_client_ip(request)
    browser_name = _parse_browser(user_agent)
    os_name = _parse_os(user_agent)
    device_label = _build_device_label(user_agent)

    session = None
    if device_id:
        session = (
            AuthSession.objects.select_for_update()
            .filter(user=user, device_id=device_id)
            .first()
        )

    if not session:
        session = AuthSession.objects.select_for_update().filter(refresh_jti=jti).first()

    if not session:
        session = AuthSession(user=user)

    session.refresh_jti = jti
    session.access_jti = access_jti
    session.device_id = device_id or session.device_id
    session.device_label = device_label
    session.browser_name = browser_name
    session.os_name = os_name
    session.remember_me = remember_me
    session.user_agent = user_agent
    session.ip_address = ip_address
    session.is_active = True
    session.revoked_at = None
    session.last_seen_at = timezone.now()
    session.expires_at = expires_at
    session.save()

    return session


@transaction.atomic
def rotate_session_refresh(
    *,
    old_refresh_token: str,
    new_refresh_token: str,
    request,
    device_id: str = "",
    new_access_jti: str = "",
) -> Optional[AuthSession]:
    old_jti, _, user_id = _get_jti_and_exp(old_refresh_token)
    new_jti, new_expires_at, _ = _get_jti_and_exp(new_refresh_token)

    user = CustomUser.objects.filter(id=user_id).first()
    if not user:
        return None

    session = AuthSession.objects.select_for_update().filter(refresh_jti=old_jti).first()

    if not session and device_id:
        session = (
            AuthSession.objects.select_for_update()
            .filter(user=user, device_id=device_id)
            .first()
        )

    if not session:
        session = AuthSession(user=user)

    user_agent = request.META.get("HTTP_USER_AGENT", "") if request else ""
    ip_address = _extract_client_ip(request)

    # Prefer fresh UA data but fall back to whatever was stored at login
    resolved_ua = user_agent or session.user_agent

    session.refresh_jti = new_jti
    session.access_jti = new_access_jti
    session.device_id = device_id or session.device_id
    session.device_label = _build_device_label(resolved_ua, session.device_label if session.pk else "")
    session.browser_name = _parse_browser(resolved_ua) or session.browser_name
    session.os_name = _parse_os(resolved_ua) or session.os_name
    # remember_me never changes during rotation — preserve whatever was set at login
    session.user_agent = resolved_ua
    session.ip_address = ip_address
    session.is_active = True
    session.revoked_at = None
    session.last_seen_at = timezone.now()
    session.expires_at = new_expires_at
    session.save()

    return session


@transaction.atomic
def revoke_session_by_refresh(refresh_token: str) -> None:
    jti, _, _ = _get_jti_and_exp(refresh_token)
    session = AuthSession.objects.select_for_update().filter(refresh_jti=jti).first()
    if not session:
        return

    session.is_active = False
    session.access_jti = ""
    session.revoked_at = timezone.now()
    session.last_seen_at = timezone.now()
    session.save(update_fields=["is_active", "access_jti", "revoked_at", "last_seen_at"])

    outstanding = OutstandingToken.objects.filter(jti=session.refresh_jti).first()
    if outstanding:
        BlacklistedToken.objects.get_or_create(token=outstanding)


@transaction.atomic
def revoke_active_session_for_device(*, user, device_id: str) -> bool:
    if not device_id:
        return False

    session = (
        AuthSession.objects.select_for_update()
        .filter(user=user, device_id=device_id, is_active=True)
        .order_by("-last_seen_at")
        .first()
    )
    if not session:
        return False

    session.is_active = False
    session.access_jti = ""
    session.revoked_at = timezone.now()
    session.last_seen_at = timezone.now()
    session.save(update_fields=["is_active", "access_jti", "revoked_at", "last_seen_at"])

    outstanding = OutstandingToken.objects.filter(jti=session.refresh_jti).first()
    if outstanding:
        BlacklistedToken.objects.get_or_create(token=outstanding)

    return True


@transaction.atomic
def revoke_session_by_id(*, session_id: int, user) -> bool:
    session = (
        AuthSession.objects.select_for_update()
        .filter(id=session_id, user=user, is_active=True)
        .first()
    )
    if not session:
        return False

    session.is_active = False
    session.access_jti = ""
    session.revoked_at = timezone.now()
    session.last_seen_at = timezone.now()
    session.save(update_fields=["is_active", "access_jti", "revoked_at", "last_seen_at"])

    outstanding = OutstandingToken.objects.filter(jti=session.refresh_jti).first()
    if outstanding:
        BlacklistedToken.objects.get_or_create(token=outstanding)

    return True

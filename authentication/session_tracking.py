from datetime import datetime, timezone as dt_timezone
from typing import Optional

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


def _build_device_label(user_agent: str, explicit_label: str = "") -> str:
    if explicit_label:
        return explicit_label[:255]

    ua = (user_agent or "").lower()

    if "iphone" in ua:
        return "iPhone"
    if "ipad" in ua:
        return "iPad"
    if "android" in ua:
        return "Android device"
    if "windows" in ua:
        return "Windows device"
    if "mac os" in ua or "macintosh" in ua:
        return "Mac device"
    if "linux" in ua:
        return "Linux device"

    return "Unknown device"


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
def upsert_login_session(user, refresh_token: str, request, device_id: str = "") -> AuthSession:
    jti, expires_at, _ = _get_jti_and_exp(refresh_token)

    user_agent = request.META.get("HTTP_USER_AGENT", "") if request else ""
    ip_address = _extract_client_ip(request)
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
    session.device_id = device_id or session.device_id
    session.device_label = device_label
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

    session.refresh_jti = new_jti
    session.device_id = device_id or session.device_id
    session.device_label = _build_device_label(user_agent, session.device_label)
    session.user_agent = user_agent or session.user_agent
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
    session.revoked_at = timezone.now()
    session.last_seen_at = timezone.now()
    session.save(update_fields=["is_active", "revoked_at", "last_seen_at"])


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
    session.revoked_at = timezone.now()
    session.last_seen_at = timezone.now()
    session.save(update_fields=["is_active", "revoked_at", "last_seen_at"])

    outstanding = OutstandingToken.objects.filter(jti=session.refresh_jti).first()
    if outstanding:
        BlacklistedToken.objects.get_or_create(token=outstanding)

    return True

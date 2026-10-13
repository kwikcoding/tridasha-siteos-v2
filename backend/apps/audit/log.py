"""record(...) — one call from anywhere that changes something worth auditing."""
from datetime import date, datetime
from decimal import Decimal

from .models import AuditLog

SECRET_KEYS = {"password", "new", "current"}


def _jsonable(v):
    if isinstance(v, (Decimal, date, datetime)):
        return str(v)
    if hasattr(v, "pk"):
        return v.pk
    if isinstance(v, (list, tuple, set)):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    return v


def client_ip(request):
    if request is None:
        return None
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (fwd.split(",")[0].strip() or request.META.get("REMOTE_ADDR")) or None


def record(action, *, actor=None, target=None, target_type="", target_id="", summary="", changes=None, request=None):
    if target is not None:
        target_type = target_type or target._meta.model_name
        target_id = target_id or str(target.pk)
    clean = {k: ("•••" if k in SECRET_KEYS else _jsonable(v)) for k, v in (changes or {}).items()}
    if actor is not None and not getattr(actor, "is_authenticated", False):
        actor = None
    return AuditLog.objects.create(
        action=action, actor=actor, target_type=target_type, target_id=str(target_id), summary=summary[:300],
        changes=clean, ip=client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "")[:200] if request is not None else ""))


def diff(instance, new_values: dict) -> dict:
    """{field: [old, new]} for values that change."""
    out = {}
    for k, v in new_values.items():
        if k in SECRET_KEYS:
            out[k] = ["•••", "•••"]
            continue
        old = getattr(instance, k, None)
        if hasattr(old, "all"):            # many-to-many
            old = sorted(o.pk for o in old.all())
            v = sorted(getattr(x, "pk", x) for x in v)
        if _jsonable(old) != _jsonable(v):
            out[k] = [_jsonable(old), _jsonable(v)]
    return out

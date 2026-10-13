"""Alert jobs (Celery). Replaces the n8n automations.

- indent_changed      — after every action: tell the people who act at the new step; tell the requester
                         when their indent is sent back, rejected or closed.
- overdue_deliveries  — every 3 hours: POs past their expected date.
- pending_digest      — daily: "N indents waiting for you".
"""
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import User
from apps.indents import workflow as wf
from apps.indents.models import Indent, IndentEvent, WorkflowSettings

from . import channels
from .models import Notification


def _people_at(stage: str, indent: Indent):
    """Active people whose role acts at this step and who can see the indent's site."""
    qs = User.objects.filter(is_active=True).select_related("role")
    out = []
    for u in qs:
        if u.is_admin:
            continue   # admins can act everywhere; don't spam them with every step
        if stage in u.stage_keys and (u.all_sites or indent.site_id in u.site_ids()):
            out.append(u)
    return out


def notify(user, kind, title, body="", indent=None, dedupe_key=""):
    if dedupe_key and Notification.objects.filter(user=user, dedupe_key=dedupe_key).exists():
        return None
    link = f"/indents/{indent.pk}" if indent else ""
    n = Notification.objects.create(user=user, kind=kind, title=title, body=body, indent=indent, link=link,
                                    dedupe_key=dedupe_key)
    text = f"{title}\n{body}\n{settings.APP_URL}{link}".strip()
    delivered = {}
    if user.alert_whatsapp:
        delivered["whatsapp"] = channels.send_whatsapp(user.mobile, text)
    if user.alert_sms:
        delivered["sms"] = channels.send_sms(user.mobile, text)
    if user.alert_email and user.email:
        delivered["email"] = channels.send_email(user.email, f"SiteOS: {title}", text)
    if delivered:
        n.delivered = delivered
        n.save(update_fields=["delivered"])
    return n


@shared_task(ignore_result=True)
def indent_changed(indent_id: int, event_id: int):
    try:
        indent = Indent.objects.select_related("site", "raised_by").get(pk=indent_id)
        ev = IndentEvent.objects.select_related("by").get(pk=event_id)
    except (Indent.DoesNotExist, IndentEvent.DoesNotExist):
        return
    head = f"{indent.number} · {indent.item} · {indent.site.name}"

    # the step it moved to (indent lane or purchase lane)
    target = ev.to_stage if ev.to_stage in wf.STAGE else None
    if target and ev.to_status != "On Hold":
        step = wf.STAGE[target]
        for u in _people_at(target, indent):
            if u.pk != ev.by_id:
                notify(u, "waiting", f"Indent waiting for you — {step.short}", head, indent,
                       dedupe_key=f"wait:{indent.pk}:{ev.pk}")
        if target == "track":   # store/engineer receive while the PO is being tracked
            for u in _people_at("receive", indent):
                if u.pk != ev.by_id:
                    notify(u, "waiting", "Material on order — receive when it arrives", head, indent,
                           dedupe_key=f"recv:{indent.pk}:{ev.pk}")

    # first receipt opens the purchase lane (invoice step)
    if ev.action == "receive" and indent.pstage in wf.STAGE and indent.pstatus == "Received":
        for u in _people_at(indent.pstage, indent):
            if u.pk != ev.by_id:
                notify(u, "waiting", f"Invoice to verify — {wf.STAGE[indent.pstage].short}", head, indent,
                       dedupe_key=f"pwait:{indent.pk}:{indent.pstage}")

    # the requester hears about outcomes
    requester = indent.raised_by
    if requester.pk != ev.by_id and requester.is_active:
        if ev.action == "sendback" and ev.to_stage == "requester":
            notify(requester, "returned", "Your indent was sent back", f"{head}\nRemark: {ev.remarks}", indent)
        elif ev.action in ("reject", "cancel"):
            notify(requester, "returned", f"Your indent was {ev.label.lower()}", f"{head}\nRemark: {ev.remarks}", indent)
        elif ev.action in ("issueClose", "issue") and indent.stage == "closed":
            notify(requester, "closed", "Your indent is complete", head, indent)
        elif ev.action == "receive":
            notify(requester, "closed", "Material received for your indent", head, indent)


@shared_task(ignore_result=True)
def overdue_deliveries():
    today = timezone.localdate()
    late = Indent.objects.filter(stage="track", po_expected__lt=today).exclude(status__in=list(wf.FINAL)) \
        .select_related("site")
    for indent in late:
        days = (today - indent.po_expected).days
        body = f"{indent.number} · {indent.item} · PO {indent.po_no} ({indent.po_vendor}) · {days} day(s) late"
        recipients = set(_people_at("track", indent)) | set(_people_at("mgmt", indent))
        for u in recipients:
            notify(u, "overdue", "Delivery overdue", body, indent, dedupe_key=f"late:{indent.pk}:{today}")


@shared_task(ignore_result=True)
def pending_digest():
    cfg = WorkflowSettings.load().cfg()
    cutoff = timezone.now() - timedelta(hours=24)
    open_qs = Indent.objects.exclude(Q(status__in=list(wf.FINAL)) & Q(pstage__in=["", "closed"])) \
        .prefetch_related("history")
    open_list = [(i, i.as_engine_dict([{"action": e.action, "by": e.by_id} for e in i.history.all()])) for i in open_qs]
    today = timezone.localdate()
    for u in User.objects.filter(is_active=True).select_related("role"):
        if u.is_admin:
            continue
        who = u.as_who()
        sites = None if u.all_sites else u.site_ids()
        mine = [i for i, d in open_list
                if (sites is None or i.site_id in sites) and wf.allowed_actions(d, who, cfg)
                and i.stage_entered_at and i.stage_entered_at < cutoff]
        if mine:
            notify(u, "digest", f"{len(mine)} indent(s) waiting for you for more than a day",
                   ", ".join(i.number for i in mine[:10]), dedupe_key=f"digest:{u.pk}:{today}")

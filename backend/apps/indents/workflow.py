"""Tridasha indent & purchase workflow — the 12 steps.

Pure Python (no Django imports) so it can be unit-tested on its own and reused
by the API, the alert jobs and the reports. Ported from SiteOS v1 `workflow.js`.

Two connected lifecycles:

  INDENT    01 raise -> 02 stock -> 03 tech -> 04 mgmt -> (stock available?) -> 05 rfq
            -> 06 vendor -> 07 po -> 08 track (+09 receive) -> 10 issue & close
  PURCHASE  11 invoice -> 12 payment & close   (starts when material is first received)

An indent is a plain dict here (the model converts itself with `as_engine_dict()`):
  status, stage, pstatus, pstage, qty, approved_qty, issued_qty, purchase_qty,
  received_qty, held_from, rate, po_rate, est_rate, raised_by (user id), history (list of {action})

`who` is a dict: {"id": user id, "admin": bool, "stages": [stage keys the person's role acts on]}
`cfg` comes from `config()`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

EPS = 1e-9


@dataclass(frozen=True)
class Stage:
    n: str
    key: str
    lane: str               # 'indent' | 'purchase'
    label: str
    short: str
    dept: str
    actions: tuple
    done: str = ""          # status set by 'approve' at this step
    pseudo: bool = False    # no pointer stops here (people act while the indent sits at another step)
    required: bool = False  # can't be switched off in settings
    can_qty: bool = False   # approver may reduce the quantity


STAGES: list[Stage] = [
    Stage("02", "stock", "indent", "Verify stock & open orders", "Stock & open orders", "Storekeeper",
          ("approve", "sendback", "hold"), done="Under Verification"),
    Stage("03", "tech", "indent", "Verify technical requirement", "Technical", "Project Head",
          ("approve", "reject", "sendback", "hold"), done="Under Verification", can_qty=True),
    Stage("04", "mgmt", "indent", "Approve requirement & budget", "Requirement & budget", "Authorised approver / Management",
          ("approve", "reject", "sendback", "hold"), done="Approved", can_qty=True),
    Stage("—", "avail", "indent", "Stock available? Issue from stores / purchase the balance", "Stock available?", "Storekeeper",
          ("issue", "purchase"), required=True),
    Stage("05", "rfq", "indent", "Obtain vendor quotations", "Quotations", "Purchase team",
          ("approve", "hold", "reject"), done="RFQ"),
    Stage("06", "vendor", "indent", "Compare & approve supplier", "Supplier approval", "Purchase team + Authorised approver",
          ("approve", "rejectVendor", "hold"), done="Vendor Approved"),
    Stage("07", "po", "indent", "Issue purchase order", "Purchase order", "Purchase team",
          ("po", "hold"), done="PO Issued", required=True),
    Stage("08", "track", "indent", "Track material delivery", "Delivery", "Purchase team",
          ("track", "cancelBalance"), required=True),
    Stage("09", "receive", "indent", "Receive & inspect material", "Receive & inspect", "Stores + Site Engineer / QA",
          ("receive", "rejectReceipt"), pseudo=True, required=True),
    Stage("10", "issue", "indent", "Issue material & close indent", "Issue & close", "Stores + Requesting team",
          ("issueClose",), required=True),
    Stage("11", "invoice", "purchase", "Verify supplier invoice", "Invoice", "Accounts + Purchase team",
          ("verifyInv", "holdInv", "returnInv")),
    Stage("12", "payment", "purchase", "Settle payment & close purchase", "Payment", "Accounts + Authorised owner",
          ("pay", "holdPay")),
]
STAGE = {s.key: s for s in STAGES}
INDENT_STAGES = [s for s in STAGES if s.lane == "indent"]
PURCHASE_STAGES = [s for s in STAGES if s.lane == "purchase"]
PURCHASE_ACTIONS = {"verifyInv", "holdInv", "returnInv", "pay", "holdPay"}
NEEDS_REMARK = {"reject", "sendback", "hold", "rejectVendor", "rejectReceipt", "cancel", "cancelBalance",
                "holdInv", "returnInv", "holdPay"}
FINAL = {"Closed", "Stock Issued", "Rejected", "Cancelled"}
BEFORE_PO = {"requester", "stock", "tech", "mgmt", "avail", "rfq", "vendor"}
NON_APPROVAL = {"raise", "resubmit", "edit", "sendback", "hold", "resume"}

ACTION_LABEL = {
    "raise": "Raised", "resubmit": "Resubmitted", "approve": "Approved", "reject": "Rejected",
    "sendback": "Sent back", "hold": "Put on hold", "resume": "Resumed", "issue": "Issued from stock",
    "purchase": "Purchase required", "rejectVendor": "Supplier selection rejected", "po": "PO issued",
    "track": "Delivery update", "cancelBalance": "Balance cancelled", "receive": "Received & inspected",
    "rejectReceipt": "Delivery rejected — supplier return / replacement", "issueClose": "Issued to site & indent closed",
    "cancel": "Cancelled", "verifyInv": "Invoice verified", "holdInv": "Invoice on hold", "returnInv": "Invoice returned",
    "pay": "Payment settled — purchase closed", "holdPay": "Payment on hold",
}

# Fields each step may fill in together with its action (model field names).
STAGE_FIELDS = {
    "stock": {"stock_note", "stock_seen"},
    "tech": {"spec_note"},
    "mgmt": {"boq_ref", "budget_note"},
    "avail": {"stock_seen"},
    "rfq": {"quotes", "purchase_note"},
    "vendor": {"vendor_final", "rate", "lead_days", "vendor_note"},
    "po": {"po_no", "po_date", "po_vendor", "po_rate", "po_expected"},
    "track": {"tracking", "po_expected"},
    "issue": {"issued_to"},
    "invoice": {"inv_no", "inv_date", "inv_amount", "inv_gst", "inv_note"},
    "payment": {"paid_on", "pay_mode", "pay_ref", "pay_amount"},
}
RECEIVE_FIELDS = {"grn_no", "inspection"}
REQUEST_FIELDS = {"site", "item", "item_code", "unit", "qty", "need_by", "priority", "purpose", "est_rate"}

# Default steps for the built-in roles.
DEFAULT_ROLE_STAGES = {
    "admin": [s.key for s in STAGES],
    "pm": ["tech"],
    "qs": [],
    "engineer": ["receive"],
    "purchase": ["rfq", "po", "track", "invoice"],
    "management": ["mgmt", "vendor", "payment"],
    "supervisor": [],
    "store": ["stock", "avail", "receive", "issue"],
    "accounts": ["invoice", "payment"],
    "safety": [],
    "viewer": [],
}


class WorkflowError(Exception):
    """Raised when an action isn't allowed or its inputs are wrong. Message is user-facing."""


# ---------------------------------------------------------------- helpers
def _num(v) -> float:
    try:
        return float(v) if v not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def _blank(v) -> bool:
    return v is None or v == ""


def need(i: dict) -> float:
    return _num(i.get("qty") if _blank(i.get("approved_qty")) else i.get("approved_qty"))


def to_buy(i: dict) -> float:
    if not _blank(i.get("purchase_qty")):
        return _num(i.get("purchase_qty"))
    return need(i) - _num(i.get("issued_qty"))


def indent_value(i: dict) -> float:
    return need(i) * _num(i.get("po_rate") or i.get("rate") or i.get("est_rate"))


def is_final(i: dict) -> bool:
    return i.get("status") in FINAL or i.get("stage") == "closed"


def purchase_open(i: dict) -> bool:
    return bool(i.get("pstage")) and i.get("pstage") != "closed"


def _r3(x: float) -> float:
    return round(x * 1000) / 1000


# ---------------------------------------------------------------- configuration
@dataclass
class Config:
    on: dict = field(default_factory=dict)
    mgmt_limit: float = 0.0     # 0 = every indent goes to management
    mgmt_never: bool = False


def config(doc: dict | None = None) -> Config:
    """doc = {"stages": {key: {"on": bool}}, "mgmt_limit": number | "never" | None}"""
    doc = doc or {}
    st = doc.get("stages") or {}
    on = {s.key: True if s.required else not (st.get(s.key, {}).get("on") is False) for s in STAGES}
    raw = doc.get("mgmt_limit")
    never = raw == "never"
    lim = 0.0 if never or _blank(raw) else _num(raw)
    return Config(on=on, mgmt_limit=max(lim, 0.0), mgmt_never=never)


def stage_on(i: dict, cfg: Config, s: Stage) -> bool:
    if not cfg.on.get(s.key, True):
        return False
    if s.key == "mgmt":
        return not cfg.mgmt_never and indent_value(i) >= cfg.mgmt_limit
    return True


def stages_for(i: dict, cfg: Config) -> list[Stage]:
    return [s for s in STAGES if stage_on(i, cfg, s)]


def pointer_stages(i: dict, cfg: Config) -> list[Stage]:
    return [s for s in INDENT_STAGES if not s.pseudo and stage_on(i, cfg, s)]


def first_stage(i: dict, cfg: Config) -> str:
    return pointer_stages(i, cfg)[0].key


def next_stage(i: dict, cfg: Config, frm: str) -> str:
    keys = [s.key for s in pointer_stages(i, cfg)]
    if frm in keys and keys.index(frm) < len(keys) - 1:
        return keys[keys.index(frm) + 1]
    return "closed"


def prev_stage(i: dict, cfg: Config, frm: str) -> str:
    keys = [s.key for s in pointer_stages(i, cfg) if s.key in {"stock", "tech", "mgmt", "rfq", "vendor"}]
    if frm in keys and keys.index(frm) > 0:
        return keys[keys.index(frm) - 1]
    return "requester"


def first_purchase(cfg: Config) -> str:
    return next((s.key for s in PURCHASE_STAGES if cfg.on.get(s.key)), "closed")


def next_purchase(cfg: Config, frm: str) -> str:
    keys = [s.key for s in PURCHASE_STAGES if cfg.on.get(s.key)]
    if frm in keys and keys.index(frm) < len(keys) - 1:
        return keys[keys.index(frm) + 1]
    return "closed"


# ---------------------------------------------------------------- who may do what
def is_requester(i: dict, who: dict) -> bool:
    return who is not None and i.get("raised_by") == who.get("id")


def acts_at(who: dict, stage: str) -> bool:
    return bool(who) and (who.get("admin") or stage in (who.get("stages") or []))


def has_approval(i: dict) -> bool:
    return any(h.get("action") not in NON_APPROVAL for h in i.get("history") or [])


def allowed_actions(i: dict, who: dict, cfg: Config) -> list[str]:
    out: list[str] = []

    def add(*acts):
        for a in acts:
            if a not in out:
                out.append(a)

    stage = i.get("stage")
    if not is_final(i) and stage:
        if stage != "requester" and stage not in STAGE:
            if who.get("admin"):
                add("cancel")
        elif stage == "requester":
            if is_requester(i, who) or who.get("admin"):
                add("resubmit", "cancel")
        elif i.get("status") == "On Hold":
            if acts_at(who, stage):
                add("resume", "reject")
        else:
            if acts_at(who, stage):
                add(*STAGE[stage].actions)
            if stage == "track" and acts_at(who, "receive"):
                add("receive", "rejectReceipt")
            if stage == "issue" and is_requester(i, who):
                add("issueClose")
            if not has_approval(i) and stage == first_stage(i, cfg) and is_requester(i, who):
                add("cancel")
            if who.get("admin") and stage in BEFORE_PO:
                add("cancel")
    if purchase_open(i) and acts_at(who, i["pstage"]) and i["pstage"] in STAGE:
        add(*STAGE[i["pstage"]].actions)
    return out


def can_edit_request(i: dict, who: dict, cfg: Config) -> bool:
    if is_final(i) or not i.get("stage"):
        return False
    if who.get("admin") and i["stage"] in BEFORE_PO:
        return True
    if not is_requester(i, who):
        return False
    return i["stage"] == "requester" or (
        i["stage"] == first_stage(i, cfg) and not has_approval(i) and i.get("status") == "Requested")


# ---------------------------------------------------------------- transitions
def transition(i: dict, action: str, entry: dict, cfg: Config) -> dict:
    """Return {"status","stage","pstatus","pstage","extra"}; raise WorkflowError if not possible."""
    st = i.get("stage")

    def ok(status, stage, extra=None):
        return {"status": status, "stage": stage, "pstatus": i.get("pstatus") or "", "pstage": i.get("pstage") or "",
                "extra": extra or {}}

    def pok(pstatus, pstage, extra=None):
        return {"status": i.get("status"), "stage": st, "pstatus": pstatus, "pstage": pstage, "extra": extra or {}}

    if action == "approve":
        s = STAGE.get(st)
        if not s or s.lane != "indent" or not s.done:
            raise WorkflowError("Nothing to approve here.")
        tmp = dict(i)
        if entry.get("qty_to") is not None:
            tmp["approved_qty"] = entry["qty_to"]
        return ok(s.done, next_stage(tmp, cfg, st))
    if action == "reject":
        return ok("Rejected", "closed")
    if action == "sendback":
        return ok("Sent Back", prev_stage(i, cfg, st) if entry.get("to") == "previous" else "requester")
    if action == "hold":
        return ok("On Hold", st, {"held_from": i.get("status")})
    if action == "resume":
        return ok(i.get("held_from") or "Requested", st, {"held_from": ""})
    if action == "cancel":
        return ok("Cancelled", "closed")
    if action == "resubmit":
        return ok("Requested", first_stage(i, cfg), {"approved_qty": None})
    if action in ("issue", "purchase"):
        q = 0.0 if action == "purchase" else _num(entry.get("qty"))
        if action == "issue" and not q > 0:
            raise WorkflowError("Enter the quantity issued from stock.")
        nd = need(i)
        if q > nd + EPS:
            raise WorkflowError("You can’t issue more than the approved quantity.")
        if q + EPS >= nd:
            return ok("Stock Issued", "closed", {"issued_qty": q, "purchase_qty": 0, "close_reason": "Fully issued from stock"})
        return ok("Purchase Required", next_stage(i, cfg, "avail"), {"issued_qty": q, "purchase_qty": _r3(nd - q)})
    if action == "rejectVendor":
        return ok("Supplier Rejected", "rfq" if cfg.on.get("rfq") else "vendor")
    if action == "po":
        return ok("PO Issued", "track")
    if action == "track":
        return ok("In Transit", "track")
    if action == "receive":
        q = _num(entry.get("qty"))
        if not q > 0:
            raise WorkflowError("Enter the accepted quantity.")
        got = _num(i.get("received_qty")) + q
        r = ok("Received", "issue", {"received_qty": got}) if got + EPS >= to_buy(i) \
            else ok("Partially Received", "track", {"received_qty": got})
        if not i.get("pstage"):
            fp = first_purchase(cfg)
            r["pstage"], r["pstatus"] = fp, ("Purchase Closed" if fp == "closed" else "Received")
        return r
    if action == "rejectReceipt":
        return ok("Supplier Return / Replacement", "track")
    if action == "cancelBalance":
        got = _num(i.get("received_qty"))
        if not got > 0:
            raise WorkflowError("Nothing received yet — cancel the indent instead.")
        return ok("Received", "issue", {"balance_cancelled": _r3(to_buy(i) - got), "purchase_qty": got})
    if action == "issueClose":
        return ok("Closed", "closed")
    if action == "verifyInv":
        n = next_purchase(cfg, "invoice")
        return pok("Purchase Closed" if n == "closed" else "Invoice Verified", n)
    if action == "holdInv":
        return pok("Invoice On Hold", i.get("pstage"))
    if action == "returnInv":
        return pok("Invoice Returned", i.get("pstage"))
    if action == "pay":
        return pok("Purchase Closed", "closed")
    if action == "holdPay":
        return pok("Payment On Hold", i.get("pstage"))
    raise WorkflowError("Unknown action.")


def fields_for_action(i: dict, action: str) -> set[str]:
    """Which data fields a person may fill in together with this action."""
    lane_stage = i.get("pstage") if action in PURCHASE_ACTIONS else i.get("stage")
    allowed = set(STAGE_FIELDS.get(lane_stage, set()))
    if action in ("receive", "rejectReceipt"):
        allowed |= RECEIVE_FIELDS
    if action == "resubmit":
        allowed |= REQUEST_FIELDS
    return allowed


def check_inputs(i: dict, action: str, entry: dict, data: dict) -> None:
    """Required inputs for particular actions. `data` = fields after merging what was sent."""
    if action in NEEDS_REMARK and not str(entry.get("remarks") or "").strip():
        raise WorkflowError("Please write a remark for this action.")
    if action == "approve" and entry.get("qty_to") is not None:
        s = STAGE.get(i.get("stage"))
        if not (s and s.can_qty):
            raise WorkflowError("The quantity can’t be changed at this step.")
        if _num(entry["qty_to"]) <= 0:
            raise WorkflowError("Approved quantity must be more than zero.")
        if _num(entry["qty_to"]) > need(i) + EPS:
            raise WorkflowError("Approved quantity can’t be more than requested — send it back instead.")
    if action == "approve" and i.get("stage") == "rfq":
        quotes = data.get("quotes") or []
        if not any(isinstance(q, dict) and q.get("vendor") for q in quotes):
            raise WorkflowError("Enter at least one quotation.")
    if action == "approve" and i.get("stage") == "vendor" and not (data.get("vendor_final") and _num(data.get("rate")) > 0):
        raise WorkflowError("Choose the supplier and rate being approved.")
    if action == "po" and not (data.get("po_no") and data.get("po_vendor")):
        raise WorkflowError("Enter the PO number and supplier.")
    if action == "verifyInv" and not (data.get("inv_no") and _num(data.get("inv_amount")) > 0):
        raise WorkflowError("Enter the invoice number and amount.")
    if action == "pay" and not data.get("paid_on"):
        raise WorkflowError("Enter the payment date.")


def plan(i: dict, action: str, entry: dict, data: dict, who: dict, cfg: Config) -> dict:
    """Validate an action end-to-end and return the transition result.

    i     — current indent (engine dict)
    entry — {"remarks", "qty", "qty_to", "to"}
    data  — field values sent with the action (already filtered to fields_for_action)
    """
    if action not in allowed_actions(i, who, cfg):
        at = i.get("pstage") if action in PURCHASE_ACTIONS else i.get("stage")
        step = STAGE[at].short if at in STAGE else (at or "—")
        raise WorkflowError(f"Your role can’t do “{ACTION_LABEL.get(action, action)}” at the {step} step.")
    merged = {**i, **data}
    check_inputs(merged, action, entry, merged)
    return transition(merged, action, entry, cfg)


def waiting_with(i: dict) -> str:
    if is_final(i):
        return ""
    if i.get("stage") == "requester":
        return "Requester"
    s = STAGE.get(i.get("stage"))
    return s.dept if s else (i.get("stage") or "")


def purchase_with(i: dict) -> str:
    if not purchase_open(i):
        return ""
    s = STAGE.get(i.get("pstage"))
    return s.dept if s else i.get("pstage")

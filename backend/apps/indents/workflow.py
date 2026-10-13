"""Tridasha indent & purchase workflow — the 12 steps.

Pure Python (no Django imports) so it can be unit-tested on its own and reused
by the API, the alert jobs and the reports. Ported from SiteOS v1 `workflow.js`.

Two connected lifecycles:

  INDENT    01 raise -> 02 stock -> 03 tech -> 04 mgmt -> (stock available?) -> 05 rfq
            -> 06 vendor -> 07 po -> 08 track (+09 receive) -> 10 issue & close
  PURCHASE  11 invoice -> 12 payment & close   (starts when material is first received)

An indent is a plain dict here (the model converts itself with `as_engine_dict()`):
  status, stage, pstatus, pstage, qty, approved_qty, issued_qty, purchase_qty,
  received_qty, held_from, rate, po_rate, est_rate, inv_amount, inv_gst, pay_auth_amount, paid_total,
  raised_by (user id), history (list of {action})

Money controls (steps 11–12):
  11  the invoice (before GST) is matched against PO rate × quantity received (GRN); a difference beyond
      the tolerance needs a written reason and is recorded.
  12a the authoriser records the amount authorised — never more than the verified invoice (incl. GST).
  12b settlements can be partial; the total paid can never exceed the amount authorised. The purchase
      closes when the authorised amount is fully paid.

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
    approve_label: str = "Approve"


STAGES: list[Stage] = [
    Stage("02", "stock", "indent", "Verify stock & open orders", "Stock & open orders", "Storekeeper",
          ("approve", "sendback", "hold"), done="Under Verification", approve_label="Verified — forward"),
    Stage("03", "tech", "indent", "Verify technical requirement", "Technical", "Project Head",
          ("approve", "reject", "sendback", "hold"), done="Under Verification", approve_label="Approve technically", can_qty=True),
    Stage("04", "mgmt", "indent", "Approve requirement & budget", "Requirement & budget", "Authorised approver / Management",
          ("approve", "reject", "sendback", "hold"), done="Approved", approve_label="Approve requirement & budget", can_qty=True),
    Stage("—", "avail", "indent", "Stock available? Issue from stores / purchase the balance", "Stock available?", "Storekeeper",
          ("issue", "purchase"), required=True),
    Stage("05", "rfq", "indent", "Obtain vendor quotations", "Quotations", "Purchase team",
          ("approve", "hold", "reject"), done="RFQ", approve_label="Submit quotations"),
    Stage("06", "vendor", "indent", "Compare & approve supplier", "Supplier approval", "Purchase team + Authorised approver",
          ("approve", "rejectVendor", "hold"), done="Vendor Approved", approve_label="Approve supplier"),
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
    Stage("12a", "payauth", "purchase", "Authorise payment", "Authorise payment", "Management / Authorised approver",
          ("authorizePay", "holdPay"), required=True),
    Stage("12b", "payment", "purchase", "Settle payment & close purchase", "Settle payment", "Accounts",
          ("pay", "holdPay")),
]
STAGE = {s.key: s for s in STAGES}
INDENT_STAGES = [s for s in STAGES if s.lane == "indent"]
PURCHASE_STAGES = [s for s in STAGES if s.lane == "purchase"]
PURCHASE_ACTIONS = {"verifyInv", "holdInv", "returnInv", "authorizePay", "pay", "holdPay"}
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
    "authorizePay": "Payment authorised", "pay": "Payment recorded", "holdPay": "Payment on hold",
}

# Order in which the action forms show the fields.
FIELD_ORDER = ["stock_seen", "stock_note", "spec_note", "boq_ref", "budget_note", "quotes", "purchase_note",
               "vendor_final", "rate", "lead_days", "vendor_note", "po_no", "po_date", "po_vendor", "po_rate", "po_expected",
               "tracking", "grn_no", "inspection", "issued_to", "inv_no", "inv_date", "inv_amount", "inv_gst", "inv_note",
               "pay_auth_amount", "paid_on", "pay_mode", "pay_ref", "pay_amount"]

# What the buttons say (the history uses ACTION_LABEL, in the past tense).
BUTTON_LABEL = {
    "resubmit": "Resubmit", "approve": "Approve", "reject": "Reject", "sendback": "Send back", "hold": "Put on hold",
    "resume": "Resume", "issue": "Issue from stock", "purchase": "Purchase all (none in stock)",
    "rejectVendor": "Reject supplier selection", "po": "Issue PO", "track": "Update delivery",
    "cancelBalance": "Cancel the balance", "receive": "Receive material", "rejectReceipt": "Reject delivery",
    "issueClose": "Issue to site & close", "cancel": "Cancel indent", "verifyInv": "Invoice verified",
    "holdInv": "Hold invoice", "returnInv": "Return invoice", "authorizePay": "Authorise payment",
    "pay": "Record payment", "holdPay": "Hold payment",
}

# Fields each step may fill in together with its action (model field names).
STAGE_FIELDS = {
    "stock": {"stock_note", "stock_seen"},
    "tech": {"spec_note"},
    "mgmt": {"boq_ref", "budget_note"},
    "rfq": {"quotes", "purchase_note"},
    "vendor": {"vendor_final", "rate", "lead_days", "vendor_note"},
    "po": {"po_no", "po_date", "po_vendor", "po_rate", "po_expected"},
    "track": {"tracking", "po_expected"},
    "issue": {"issued_to"},
    "invoice": {"inv_no", "inv_date", "inv_amount", "inv_gst", "inv_note"},
    "payauth": {"pay_auth_amount"},
    "payment": {"paid_on", "pay_mode", "pay_ref", "pay_amount"},
}
RECEIVE_FIELDS = {"grn_no", "inspection"}
# actions that only take a remark (no step data)
REMARK_ONLY = {"reject", "sendback", "hold", "resume", "cancel", "rejectVendor", "purchase", "cancelBalance",
               "holdInv", "returnInv", "holdPay"}
REQUEST_FIELDS = {"site", "material", "item", "item_code", "unit", "qty", "need_by", "priority", "purpose", "est_rate"}

# Default steps for the built-in roles.
DEFAULT_ROLE_STAGES = {
    "admin": [s.key for s in STAGES],
    "pm": ["tech"],
    "qs": [],
    "engineer": ["receive", "issue"],
    "purchase": ["rfq", "po", "track", "invoice"],
    "management": ["mgmt", "vendor", "payauth"],
    "supervisor": [],
    "store": ["stock", "avail", "receive", "issue"],
    "accounts": ["invoice", "payment"],
    "safety": [],
    "viewer": [],
}


# Default limits inside a step: Purchase coordinates the invoice step but only the Accountant verifies it.
DEFAULT_STEP_ACTIONS = {
    "purchase": {"invoice": ["holdInv", "returnInv"]},
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


def _r2(x: float) -> float:
    return round(x * 100) / 100


MONEY_EPS = 0.005


def expected_invoice(i: dict) -> float:
    """Step 11 three-way match basis: PO rate (or approved rate) × quantity received on GRNs, before GST."""
    return _r2(_num(i.get("po_rate") or i.get("rate")) * _num(i.get("received_qty")))


def invoice_total(i: dict) -> float:
    return _r2(_num(i.get("inv_amount")) + _num(i.get("inv_gst")))


def payable(i: dict) -> float:
    """What may be authorised: the verified invoice incl. GST; without an invoice step, the PO × GRN value."""
    return invoice_total(i) if _num(i.get("inv_amount")) > 0 else expected_invoice(i)


def pay_limit(i: dict, cfg: "Config") -> float:
    """The most that may be paid in total: the amount authorised at 12a (or what is payable if 12a never ran)."""
    auth = _num(i.get("pay_auth_amount"))
    return auth if auth > 0 else payable(i)


def outstanding(i: dict, cfg: "Config") -> float:
    return _r2(max(pay_limit(i, cfg) - _num(i.get("paid_total")), 0.0))


def invoice_variance(i: dict, cfg: "Config") -> tuple[float, float, bool]:
    """→ (expected, difference, within tolerance)."""
    exp = expected_invoice(i)
    diff = _r2(_num(i.get("inv_amount")) - exp)
    if exp <= 0:
        return exp, diff, False
    return exp, diff, abs(diff) <= max(exp * cfg.inv_tolerance_pct / 100.0, 1.0) + MONEY_EPS


# ---------------------------------------------------------------- configuration
@dataclass
class Config:
    on: dict = field(default_factory=dict)
    mgmt_limit: float = 0.0     # 0 = every indent goes to management
    mgmt_never: bool = False
    inv_tolerance_pct: float = 1.0   # step 11: invoice may differ from PO × GRN by this much without a reason


def config(doc: dict | None = None) -> Config:
    """doc = {"stages": {key: {"on": bool}}, "mgmt_limit": number | "never" | None}"""
    doc = doc or {}
    st = doc.get("stages") or {}
    on = {s.key: True if s.required else not (st.get(s.key, {}).get("on") is False) for s in STAGES}
    raw = doc.get("mgmt_limit")
    never = raw == "never"
    lim = 0.0 if never or _blank(raw) else _num(raw)
    tol = doc.get("inv_tolerance_pct")
    tol = 1.0 if _blank(tol) else max(_num(tol), 0.0)
    return Config(on=on, mgmt_limit=max(lim, 0.0), mgmt_never=never, inv_tolerance_pct=tol)


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


def step_allows(who: dict, stage: str, action: str) -> bool:
    """A role can be limited to some of a step's actions (e.g. Purchase may only hold or return an invoice)."""
    if who.get("admin"):
        return True
    lim = (who.get("limits") or {}).get(stage)
    return lim is None or action in lim


def payment_authoriser(i: dict):
    """Who authorised the payment (the last authorisation in the history), if anyone."""
    for h in reversed(i.get("history") or []):
        if h.get("action") == "authorizePay":
            return h.get("by")
    return None


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
                add(*[a for a in STAGE[stage].actions if step_allows(who, stage, a)])
            if stage == "track" and acts_at(who, "receive"):
                add(*[a for a in ("receive", "rejectReceipt") if step_allows(who, "receive", a)])
            if stage == "issue" and is_requester(i, who):
                add("issueClose")
            if not has_approval(i) and stage == first_stage(i, cfg) and is_requester(i, who):
                add("cancel")
            if who.get("admin") and stage in BEFORE_PO:
                add("cancel")
    if purchase_open(i) and acts_at(who, i["pstage"]) and i["pstage"] in STAGE:
        add(*[a for a in STAGE[i["pstage"]].actions if step_allows(who, i["pstage"], a)])
    # separation of duties: whoever authorised the payment can't also settle it — administrator included
    if "pay" in out and payment_authoriser(i) is not None and payment_authoriser(i) == who.get("id"):
        out.remove("pay")
    return out


def is_override(i: dict, who: dict, action: str, cfg: "Config") -> bool:
    """True when only the administrator's override power allows this action."""
    if not who.get("admin"):
        return False
    return action not in allowed_actions(i, {**who, "admin": False}, cfg)


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
        exp, diff, _ = invoice_variance(i, cfg)
        return pok("Purchase Closed" if n == "closed" else "Invoice Verified", n,
                   {"inv_expected": exp if exp > 0 else None})
    if action == "authorizePay":
        n = next_purchase(cfg, "payauth")
        return pok("Purchase Closed" if n == "closed" else "Payment Authorised", n,
                   {"pay_auth_amount": _num(i.get("pay_auth_amount"))})
    if action == "holdInv":
        return pok("Invoice On Hold", i.get("pstage"))
    if action == "returnInv":
        return pok("Invoice Returned", i.get("pstage"))
    if action == "pay":
        paid = _r2(_num(i.get("paid_total")) + _num(i.get("pay_amount")))
        if paid + MONEY_EPS >= pay_limit(i, cfg):
            return pok("Purchase Closed", "closed", {"paid_total": paid})
        return pok("Part Paid", "payment", {"paid_total": paid})
    if action == "holdPay":
        return pok("Payment On Hold", i.get("pstage"))
    raise WorkflowError("Unknown action.")


def fields_for_action(i: dict, action: str) -> set[str]:
    """Which data fields a person may fill in together with this action."""
    if action in REMARK_ONLY:
        return set()
    if action in ("receive", "rejectReceipt"):
        return set(RECEIVE_FIELDS)
    lane_stage = i.get("pstage") if action in PURCHASE_ACTIONS else i.get("stage")
    allowed = set(STAGE_FIELDS.get(lane_stage, set()))
    if action in ("receive", "rejectReceipt"):
        allowed |= RECEIVE_FIELDS
    if action == "resubmit":
        allowed |= REQUEST_FIELDS
    return allowed


def check_inputs(i: dict, action: str, entry: dict, data: dict, cfg: "Config | None" = None) -> None:
    """Required inputs for particular actions. `data` = fields after merging what was sent."""
    cfg = cfg or config()
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
    if action == "verifyInv":
        if not (data.get("inv_no") and _num(data.get("inv_amount")) > 0):
            raise WorkflowError("Enter the invoice number and amount.")
        if _num(data.get("inv_gst")) < 0:
            raise WorkflowError("GST can’t be negative.")
        exp, diff, ok_ = invoice_variance(data, cfg)
        if not ok_ and not str(entry.get("remarks") or "").strip():
            if exp <= 0:
                raise WorkflowError("There is no PO rate × received quantity to match this invoice against — "
                                    "write the reason in Remarks to verify it anyway.")
            raise WorkflowError(f"Invoice (before GST) differs from PO rate × received quantity (₹{exp:,.2f}) by "
                                f"₹{diff:,.2f} — more than the {cfg.inv_tolerance_pct:g}% tolerance. Write the reason in "
                                "Remarks to verify it anyway, or hold / return the invoice.")
    if action == "authorizePay":
        amt = _num(data.get("pay_auth_amount"))
        cap = payable(data)
        if amt <= 0:
            raise WorkflowError("Enter the amount being authorised.")
        if cap > 0 and amt > cap + MONEY_EPS:
            raise WorkflowError(f"You can’t authorise more than the verified invoice (₹{cap:,.2f} incl. GST).")
    if action == "pay":
        if not data.get("paid_on"):
            raise WorkflowError("Enter the payment date.")
        amt = _num(data.get("pay_amount"))
        if amt <= 0:
            raise WorkflowError("Enter the amount paid.")
        left = outstanding(data, cfg)
        if amt > left + MONEY_EPS:
            raise WorkflowError(f"That is more than the ₹{left:,.2f} still authorised for payment — "
                                "excess payments aren’t allowed.")


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
    override = is_override(i, who, action, cfg)
    if override and not str(entry.get("remarks") or "").strip():
        raise WorkflowError("You’re acting as administrator outside your own role — write the reason in Remarks. "
                            "It is recorded as an override.")
    merged = {**i, **data}
    check_inputs(merged, action, entry, merged, cfg)
    t = transition(merged, action, entry, cfg)
    t["override"] = override
    return t


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

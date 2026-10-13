"""Engine tests — plain unittest, no database needed.

Run:  python -m unittest apps.indents.tests.test_workflow   (from backend/)
"""
import unittest

from apps.indents import workflow as wf

ADMIN = {"id": 1, "admin": True, "stages": []}
ENGINEER = {"id": 10, "admin": False, "stages": wf.DEFAULT_ROLE_STAGES["engineer"]}
STORE = {"id": 11, "admin": False, "stages": wf.DEFAULT_ROLE_STAGES["store"]}
PM = {"id": 12, "admin": False, "stages": wf.DEFAULT_ROLE_STAGES["pm"]}
MGMT = {"id": 13, "admin": False, "stages": wf.DEFAULT_ROLE_STAGES["management"]}
PURCHASE = {"id": 14, "admin": False, "stages": wf.DEFAULT_ROLE_STAGES["purchase"]}
ACCOUNTS = {"id": 15, "admin": False, "stages": wf.DEFAULT_ROLE_STAGES["accounts"]}


def new_indent(cfg, qty=100, **kw):
    i = {"qty": qty, "raised_by": ENGINEER["id"], "status": "Requested", "history": [{"action": "raise"}],
         "est_rate": 400, **kw}
    i["stage"] = wf.first_stage(i, cfg)
    return i


def act(i, who, action, cfg, entry=None, data=None):
    entry, data = entry or {}, data or {}
    t = wf.plan(i, action, entry, data, who, cfg)
    n = {**i, **data, "status": t["status"], "stage": t["stage"], "pstatus": t["pstatus"], "pstage": t["pstage"]}
    n.update(t["extra"])
    if action == "approve" and entry.get("qty_to") is not None:
        n["approved_qty"] = entry["qty_to"]
    n["history"] = i["history"] + [{"action": action}]
    return n


class FullPurchaseFlow(unittest.TestCase):
    def test_all_12_steps(self):
        cfg = wf.config()
        i = new_indent(cfg)
        self.assertEqual(i["stage"], "stock")
        i = act(i, STORE, "approve", cfg)
        self.assertEqual((i["stage"], i["status"]), ("tech", "Under Verification"))
        i = act(i, PM, "approve", cfg, {"qty_to": 80})
        self.assertEqual(i["stage"], "mgmt")
        i = act(i, MGMT, "approve", cfg)
        self.assertEqual((i["stage"], i["status"]), ("avail", "Approved"))
        i = act(i, STORE, "issue", cfg, {"qty": 30})
        self.assertEqual((i["stage"], i["status"], i["purchase_qty"]), ("rfq", "Purchase Required", 50))
        i = act(i, PURCHASE, "approve", cfg, data={"quotes": [{"vendor": "Ultratech", "rate": 390}]})
        self.assertEqual(i["stage"], "vendor")
        i = act(i, MGMT, "approve", cfg, data={"vendor_final": "Ultratech", "rate": 390})
        self.assertEqual(i["stage"], "po")
        i = act(i, PURCHASE, "po", cfg, data={"po_no": "PO-1", "po_vendor": "Ultratech"})
        self.assertEqual((i["stage"], i["status"]), ("track", "PO Issued"))
        i = act(i, ENGINEER, "receive", cfg, {"qty": 20})
        self.assertEqual((i["stage"], i["status"], i["pstage"]), ("track", "Partially Received", "invoice"))
        i = act(i, STORE, "receive", cfg, {"qty": 30})
        self.assertEqual((i["stage"], i["status"], i["received_qty"]), ("issue", "Received", 50))
        i = act(i, STORE, "issueClose", cfg)
        self.assertEqual((i["stage"], i["status"]), ("closed", "Closed"))
        # purchase lane continues independently
        i = act(i, ACCOUNTS, "verifyInv", cfg, data={"inv_no": "INV-9", "inv_amount": 19500})
        self.assertEqual((i["pstage"], i["pstatus"]), ("payment", "Invoice Verified"))
        i = act(i, MGMT, "pay", cfg, data={"paid_on": "2026-10-20"})
        self.assertEqual((i["pstage"], i["pstatus"]), ("closed", "Purchase Closed"))

    def test_fully_from_stock_closes(self):
        cfg = wf.config()
        i = new_indent(cfg, qty=10)
        for who in (STORE, PM, MGMT):
            i = act(i, who, "approve", cfg)
        i = act(i, STORE, "issue", cfg, {"qty": 10})
        self.assertEqual((i["stage"], i["status"]), ("closed", "Stock Issued"))


class Permissions(unittest.TestCase):
    def test_wrong_role_blocked(self):
        cfg = wf.config()
        i = new_indent(cfg)
        with self.assertRaises(wf.WorkflowError):
            wf.plan(i, "approve", {}, {}, PM, cfg)       # PM can't act at the stock step

    def test_requester_can_cancel_before_any_approval_only(self):
        cfg = wf.config()
        i = new_indent(cfg)
        self.assertIn("cancel", wf.allowed_actions(i, ENGINEER, cfg))
        i = act(i, STORE, "approve", cfg)
        self.assertNotIn("cancel", wf.allowed_actions(i, ENGINEER, cfg))

    def test_remark_required(self):
        cfg = wf.config()
        i = new_indent(cfg)
        with self.assertRaises(wf.WorkflowError):
            wf.plan(i, "sendback", {}, {}, STORE, cfg)
        i = act(i, STORE, "sendback", cfg, {"remarks": "Check spec"})
        self.assertEqual((i["stage"], i["status"]), ("requester", "Sent Back"))
        i = act(i, ENGINEER, "resubmit", cfg)
        self.assertEqual(i["stage"], "stock")

    def test_cannot_approve_more_than_requested(self):
        cfg = wf.config()
        i = act(new_indent(cfg), STORE, "approve", cfg)
        with self.assertRaises(wf.WorkflowError):
            wf.plan(i, "approve", {"qty_to": 500}, {}, PM, cfg)


class ActionFields(unittest.TestCase):
    def test_only_progress_actions_take_step_data(self):
        i = {"stage": "vendor", "pstage": ""}
        self.assertIn("vendor_final", wf.fields_for_action(i, "approve"))
        for a in ("hold", "cancel", "rejectVendor"):
            self.assertEqual(wf.fields_for_action(i, a), set())
        self.assertEqual(wf.fields_for_action({"stage": "track"}, "receive"), {"grn_no", "inspection"})


class Settings(unittest.TestCase):
    def test_mgmt_limit_skips_small_indents(self):
        cfg = wf.config({"mgmt_limit": 100000})
        i = new_indent(cfg, qty=10, est_rate=100)            # value 1,000 < limit
        i = act(i, STORE, "approve", cfg)
        i = act(i, PM, "approve", cfg)
        self.assertEqual(i["stage"], "avail")

    def test_switch_off_rfq(self):
        cfg = wf.config({"stages": {"rfq": {"on": False}}})
        i = new_indent(cfg)
        for who in (STORE, PM, MGMT):
            i = act(i, who, "approve", cfg)
        i = act(i, STORE, "purchase", cfg)
        self.assertEqual(i["stage"], "vendor")

    def test_required_steps_cannot_be_switched_off(self):
        cfg = wf.config({"stages": {"po": {"on": False}, "avail": {"on": False}}})
        self.assertTrue(cfg.on["po"] and cfg.on["avail"])


if __name__ == "__main__":
    unittest.main()

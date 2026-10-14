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
PURCHASE = {"id": 14, "admin": False, "stages": wf.DEFAULT_ROLE_STAGES["purchase"],
            "limits": wf.DEFAULT_STEP_ACTIONS["purchase"]}
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
    n["history"] = i["history"] + [{"action": action, "by": who["id"]}]
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
        self.assertEqual((i["pstage"], i["pstatus"]), ("payauth", "Invoice Verified"))
        i = act(i, MGMT, "authorizePay", cfg, data={"pay_auth_amount": 19500})
        self.assertEqual((i["pstage"], i["pstatus"]), ("payment", "Payment Authorised"))
        i = act(i, ACCOUNTS, "pay", cfg, data={"paid_on": "2026-10-20", "pay_amount": 19500})
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


def at_invoice(cfg):
    i = new_indent(cfg)
    for who in (STORE, PM, MGMT):
        i = act(i, who, "approve", cfg)
    i = act(i, STORE, "purchase", cfg)
    i = act(i, PURCHASE, "approve", cfg, data={"quotes": [{"vendor": "V", "rate": 1}]})
    i = act(i, MGMT, "approve", cfg, data={"vendor_final": "V", "rate": 1})
    i = act(i, PURCHASE, "po", cfg, data={"po_no": "P", "po_vendor": "V"})
    return act(i, STORE, "receive", cfg, {"qty": 100})


class Controls(unittest.TestCase):
    def test_purchase_cannot_verify_invoice_only_hold_or_return(self):
        cfg = wf.config()
        i = at_invoice(cfg)
        self.assertEqual(i["pstage"], "invoice")
        self.assertEqual(wf.allowed_actions(i, PURCHASE, cfg), ["holdInv", "returnInv"])
        self.assertIn("verifyInv", wf.allowed_actions(i, ACCOUNTS, cfg))

    def test_management_authorises_accountant_settles(self):
        cfg = wf.config()
        i = act(at_invoice(cfg), ACCOUNTS, "verifyInv", cfg, data={"inv_no": "I", "inv_amount": 100})
        self.assertNotIn("pay", wf.allowed_actions(i, ACCOUNTS, cfg))       # not authorised yet
        self.assertNotIn("authorizePay", wf.allowed_actions(i, ACCOUNTS, cfg))
        i = act(i, MGMT, "authorizePay", cfg, data={"pay_auth_amount": 100})
        self.assertIn("pay", wf.allowed_actions(i, ACCOUNTS, cfg))

    def test_authoriser_cannot_settle_even_as_admin(self):
        cfg = wf.config()
        i = act(at_invoice(cfg), ACCOUNTS, "verifyInv", cfg, data={"inv_no": "I", "inv_amount": 100})
        i = act(i, ADMIN, "authorizePay", cfg, {"remarks": "Director away"}, data={"pay_auth_amount": 100})
        self.assertNotIn("pay", wf.allowed_actions(i, ADMIN, cfg))
        self.assertIn("pay", wf.allowed_actions(i, ACCOUNTS, cfg))

    def test_admin_override_needs_reason_and_is_flagged(self):
        cfg = wf.config()
        i = new_indent(cfg)
        with self.assertRaises(wf.WorkflowError):
            wf.plan(i, "approve", {}, {}, ADMIN, cfg)
        t = wf.plan(i, "approve", {"remarks": "Store keeper on leave"}, {}, ADMIN, cfg)
        self.assertTrue(t["override"])
        self.assertFalse(wf.plan(i, "approve", {}, {}, STORE, cfg)["override"])

    def test_engineer_can_close_at_step_10(self):
        cfg = wf.config()
        other_engineer = {"id": 99, "admin": False, "stages": wf.DEFAULT_ROLE_STAGES["engineer"]}
        i = at_invoice(cfg)
        self.assertEqual(i["stage"], "issue")
        self.assertIn("issueClose", wf.allowed_actions(i, other_engineer, cfg))


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


def verified(cfg, amount=100, gst=18):
    """At 12a: 100 received at rate 1 → PO × GRN = ₹100; invoice ₹100 + ₹18 GST."""
    return act(at_invoice(cfg), ACCOUNTS, "verifyInv", cfg, data={"inv_no": "I", "inv_amount": amount, "inv_gst": gst})


class MoneyControls(unittest.TestCase):
    """Step 11 three-way match and step 12 authorised-amount / settlement controls."""

    def test_invoice_matching_po_times_grn_passes_without_reason(self):
        cfg = wf.config()
        i = verified(cfg, amount=100.5)            # within the default 1 % tolerance
        self.assertEqual((i["pstage"], i["inv_expected"]), ("payauth", 100.0))

    def test_invoice_mismatch_needs_reason(self):
        cfg = wf.config()
        i = at_invoice(cfg)
        with self.assertRaises(wf.WorkflowError) as e:
            wf.plan(i, "verifyInv", {}, {"inv_no": "I", "inv_amount": 150}, ACCOUNTS, cfg)
        self.assertIn("differs", str(e.exception))
        t = wf.plan(i, "verifyInv", {"remarks": "Freight billed separately as agreed"},
                    {"inv_no": "I", "inv_amount": 150}, ACCOUNTS, cfg)
        self.assertEqual(t["pstage"], "payauth")

    def test_tolerance_is_configurable(self):
        cfg = wf.config({"inv_tolerance_pct": 10})
        i = at_invoice(cfg)
        wf.plan(i, "verifyInv", {}, {"inv_no": "I", "inv_amount": 109}, ACCOUNTS, cfg)       # inside 10 %
        with self.assertRaises(wf.WorkflowError):
            wf.plan(i, "verifyInv", {}, {"inv_no": "I", "inv_amount": 111}, ACCOUNTS, cfg)

    def test_negative_gst_refused(self):
        cfg = wf.config()
        with self.assertRaises(wf.WorkflowError):
            wf.plan(at_invoice(cfg), "verifyInv", {}, {"inv_no": "I", "inv_amount": 100, "inv_gst": -5}, ACCOUNTS, cfg)

    def test_authorise_needs_amount_and_cannot_exceed_invoice(self):
        cfg = wf.config()
        i = verified(cfg)
        with self.assertRaises(wf.WorkflowError):
            wf.plan(i, "authorizePay", {}, {}, MGMT, cfg)
        with self.assertRaises(wf.WorkflowError) as e:
            wf.plan(i, "authorizePay", {}, {"pay_auth_amount": 118.01}, MGMT, cfg)
        self.assertIn("118.00", str(e.exception))
        i = act(i, MGMT, "authorizePay", cfg, data={"pay_auth_amount": 118})
        self.assertEqual((i["pstage"], i["pay_auth_amount"]), ("payment", 118))

    def test_part_payments_then_close(self):
        cfg = wf.config()
        i = act(verified(cfg), MGMT, "authorizePay", cfg, data={"pay_auth_amount": 118})
        i = act(i, ACCOUNTS, "pay", cfg, data={"paid_on": "2026-10-20", "pay_amount": 50})
        self.assertEqual((i["pstage"], i["pstatus"], i["paid_total"]), ("payment", "Part Paid", 50))
        self.assertIn("pay", wf.allowed_actions(i, ACCOUNTS, cfg))
        i = act(i, ACCOUNTS, "pay", cfg, data={"paid_on": "2026-10-21", "pay_amount": 68})
        self.assertEqual((i["pstage"], i["pstatus"], i["paid_total"]), ("closed", "Purchase Closed", 118))

    def test_excess_payment_refused(self):
        cfg = wf.config()
        i = act(verified(cfg), MGMT, "authorizePay", cfg, data={"pay_auth_amount": 100})
        with self.assertRaises(wf.WorkflowError) as e:
            wf.plan(i, "pay", {}, {"paid_on": "2026-10-20", "pay_amount": 100.01}, ACCOUNTS, cfg)
        self.assertIn("excess", str(e.exception))
        i = act(i, ACCOUNTS, "pay", cfg, data={"paid_on": "2026-10-20", "pay_amount": 60})
        with self.assertRaises(wf.WorkflowError):
            wf.plan(i, "pay", {}, {"paid_on": "2026-10-20", "pay_amount": 41}, ACCOUNTS, cfg)

    def test_payment_needs_amount_and_date(self):
        cfg = wf.config()
        i = act(verified(cfg), MGMT, "authorizePay", cfg, data={"pay_auth_amount": 100})
        for data in ({"paid_on": "2026-10-20"}, {"pay_amount": 10}, {"paid_on": "2026-10-20", "pay_amount": 0}):
            with self.assertRaises(wf.WorkflowError):
                wf.plan(i, "pay", {}, data, ACCOUNTS, cfg)

    def test_payment_step_off_closes_at_authorisation(self):
        cfg = wf.config({"stages": {"payment": {"on": False}}})
        i = act(verified(cfg), MGMT, "authorizePay", cfg, data={"pay_auth_amount": 118})
        self.assertEqual((i["pstage"], i["pstatus"]), ("closed", "Purchase Closed"))

    def test_invoice_step_off_authorises_against_po_times_grn(self):
        cfg = wf.config({"stages": {"invoice": {"on": False}}})
        i = at_invoice(cfg)
        self.assertEqual(i["pstage"], "payauth")
        with self.assertRaises(wf.WorkflowError):
            wf.plan(i, "authorizePay", {}, {"pay_auth_amount": 101}, MGMT, cfg)
        act(i, MGMT, "authorizePay", cfg, data={"pay_auth_amount": 100})


class Receipts(unittest.TestCase):
    def test_cannot_receive_more_than_ordered(self):
        cfg = wf.config()
        i = new_indent(cfg)
        for who in (STORE, PM, MGMT):
            i = act(i, who, "approve", cfg)
        i = act(i, STORE, "purchase", cfg)
        i = act(i, PURCHASE, "approve", cfg, data={"quotes": [{"vendor": "V", "rate": 1}]})
        i = act(i, MGMT, "approve", cfg, data={"vendor_final": "V", "rate": 1})
        i = act(i, PURCHASE, "po", cfg, data={"po_no": "P", "po_vendor": "V"})
        with self.assertRaises(wf.WorkflowError):
            wf.plan(i, "receive", {"qty": 101}, {}, STORE, cfg)
        i = act(i, STORE, "receive", cfg, {"qty": 60})
        with self.assertRaises(wf.WorkflowError) as e:
            wf.plan(i, "receive", {"qty": 41}, {}, STORE, cfg)
        self.assertIn("40", str(e.exception))
        i = act(i, STORE, "receive", cfg, {"qty": 40})
        self.assertEqual((i["status"], i["received_qty"]), ("Received", 100))


class SelfApproval(unittest.TestCase):
    """Nobody approves or pays their own indent; the administrator can only as a recorded override."""

    def test_project_head_cannot_approve_own_indent_another_can(self):
        cfg = wf.config()
        i = new_indent(cfg, raised_by=PM["id"])
        i = act(i, STORE, "approve", cfg)
        self.assertEqual(i["stage"], "tech")
        self.assertNotIn("approve", wf.allowed_actions(i, PM, cfg))
        self.assertIn("sendback", wf.allowed_actions(i, PM, cfg))         # can still send it back / hold
        other_pm = {**PM, "id": 77}
        self.assertIn("approve", wf.allowed_actions(i, other_pm, cfg))

    def test_management_cannot_approve_own_budget_or_authorise_own_payment(self):
        cfg = wf.config()
        i = new_indent(cfg, raised_by=MGMT["id"])
        for who in (STORE, PM):
            i = act(i, who, "approve", cfg)
        self.assertEqual(i["stage"], "mgmt")
        with self.assertRaises(wf.WorkflowError):
            wf.plan(i, "approve", {}, {}, MGMT, cfg)
        t = wf.plan(i, "approve", {"remarks": "Director is the only approver this week"}, {}, ADMIN, cfg)
        self.assertTrue(t["override"])                                    # admin can, flagged with a reason

    def test_requester_cannot_verify_own_invoice(self):
        cfg = wf.config()
        i = at_invoice(cfg)
        i["raised_by"] = ACCOUNTS["id"]
        self.assertNotIn("verifyInv", wf.allowed_actions(i, ACCOUNTS, cfg))

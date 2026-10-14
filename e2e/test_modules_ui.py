"""Browser tests for every module on the demo data (`manage.py seed_demo` on the CI database).

Each test signs in as the role that does the work, clicks through the real screens, and checks what other roles
are refused — approvals, rejections, attachments, exports, validation messages and the audit log.
"""
import os
import re

from playwright.sync_api import Page, expect

BASE = os.environ.get("E2E_BASE", "http://localhost:4173")
PW = os.environ["E2E_PASSWORD"]
DEMO = {"engineer": "9000000001", "supervisor": "9000000002", "store": "9000000003", "pm": "9000000004",
        "management": "9000000005", "purchase": "9000000006", "accounts": "9000000007", "qs": "9000000008",
        "safety": "9000000009", "viewer": "9000000010", "admin": "9500000000"}
SITE = "Demo site (try-out data)"
DENIED = "You don’t have access to this page"


def sign_in(page: Page, role: str):
    page.goto(f"{BASE}/login")
    page.get_by_label("Mobile number").fill(DEMO[role])
    page.get_by_label("Password").fill(PW)
    with page.expect_response(lambda r: "/api/auth/login/" in r.url) as resp:
        page.get_by_role("button", name="Sign in").click()
    assert resp.value.status == 200, (role, resp.value.status)
    expect(page.get_by_text(re.compile(r"Good day"))).to_be_visible(timeout=15_000)


def sign_out(page: Page):
    page.wait_for_load_state("networkidle")
    if page.locator("[role=dialog]").count():           # close an open window (it covers the header)
        page.get_by_role("button", name="Close window").first.click()
    expect(page.locator("[role=dialog]")).to_have_count(0)
    page.get_by_role("button", name="Log out").click()
    expect(page.get_by_role("button", name="Sign in")).to_be_visible()


def act(page: Page, button: str, fields: dict | None = None, exact=True):
    """Click an action button, fill its small form, confirm."""
    page.get_by_role("button", name=button, exact=exact).click()
    for label, value in (fields or {}).items():
        page.get_by_label(label).fill(value)
    page.get_by_role("button", name="Confirm").click()


def open_row(page: Page, text: str):
    page.locator("table tbody tr", has_text=text).first.click()
    expect(page.locator("[role=dialog]")).to_be_visible()      # so "button not shown" checks aren't vacuous


def chip(page: Page, text: str):
    return page.locator("[role=dialog] span.chip", has_text=re.compile(rf"^{re.escape(text)}$")).first


def download(page: Page, link="Download Excel"):
    with page.expect_download() as d:
        page.get_by_role("link", name=link).first.click()
    path = d.value.path()
    assert os.path.getsize(path) > 500, "export file is empty"
    with open(path, "rb") as f:
        assert f.read(2) == b"PK", "export isn't an .xlsx file"


# ---------------------------------------------------------------- settings → company profile
def test_company_profile_admin_only_with_validation_logo_and_audit(page: Page, tmp_path):
    sign_in(page, "admin")
    page.goto(BASE + "/settings")
    page.get_by_label("Registered name").fill("Tridasha Infra Projects Pvt Ltd")
    page.get_by_label("GSTIN", exact=True).fill("36ABCDE1234F1Z")                 # one character short
    page.get_by_role("button", name="Save company profile").click()
    expect(page.get_by_text("GSTIN is 15 characters")).to_be_visible()
    page.get_by_label("GSTIN", exact=True).fill("36ABCDE1234F1Z5")
    page.get_by_label("PAN", exact=True).fill("ABCDE1234F")
    page.get_by_label("State", exact=True).fill("Telangana")
    page.get_by_role("button", name="Save company profile").click()
    expect(page.get_by_text("Company profile saved.")).to_be_visible()
    png = tmp_path / "logo.png"
    png.write_bytes(tiny_png())
    page.get_by_label("Logo image").set_input_files(str(png))
    page.get_by_role("button", name="Upload logo").click()
    expect(page.get_by_alt_text(re.compile("logo"))).to_be_visible()
    # the change is in the audit log
    page.goto(BASE + "/team?tab=audit")
    expect(page.get_by_text("Company profile changed").first).to_be_visible()
    sign_out(page)
    sign_in(page, "pm")
    page.goto(BASE + "/settings")
    expect(page.get_by_text(DENIED)).to_be_visible()


# ---------------------------------------------------------------- sites & projects
def test_project_head_adds_project_duplicate_refused(page: Page):
    sign_in(page, "pm")
    page.goto(BASE + "/sites")
    expect(page.locator("table", has_text="[Demo] Tower A").first).to_be_visible()
    for code, ok in [("E2EB", True), ("E2EB", False)]:
        page.get_by_role("button", name="+ Add project").click()
        page.get_by_label("Site *").select_option(label=SITE)
        page.get_by_label("Code *").fill(code)
        page.get_by_label("Project *").fill("E2E Block B")
        page.get_by_role("button", name="Save").click()
        if ok:
            expect(page.locator("table tbody tr", has_text="E2EB").first).to_be_visible()
        else:
            expect(page.get_by_text("already used at this site")).to_be_visible()
            page.keyboard.press("Escape")
    sign_out(page)
    sign_in(page, "store")
    page.goto(BASE + "/sites")
    expect(page.get_by_text(DENIED)).to_be_visible()          # store keeper has no Sites module


# ---------------------------------------------------------------- tasks
def test_task_dependency_then_assignees_complete(page: Page):
    sign_in(page, "supervisor")
    page.goto(BASE + "/tasks?tab=mine")
    open_row(page, "L5 slab concrete pour")
    act(page, "Mark done")
    expect(page.get_by_text("has to be done first")).to_be_visible()
    sign_out(page)
    sign_in(page, "engineer")
    page.goto(BASE + "/tasks?tab=mine")
    open_row(page, "L5 slab reinforcement check")
    act(page, "Mark done", {"Note": "All laps checked"})
    expect(chip(page, "Done")).to_be_visible()
    sign_out(page)
    sign_in(page, "supervisor")
    page.goto(BASE + "/tasks?tab=mine")
    open_row(page, "L5 slab concrete pour")
    act(page, "Mark done")
    expect(chip(page, "Done")).to_be_visible()
    page.keyboard.press("Escape")
    page.goto(BASE + "/tasks?tab=overdue")
    expect(page.get_by_text("L5 slab reinforcement check")).to_have_count(0)
    download(page)


# ---------------------------------------------------------------- daily progress
def test_daily_report_send_back_needs_note_then_approve(page: Page):
    sign_in(page, "pm")
    page.goto(BASE + "/dpr?tab=waiting")
    open_row(page, "Tower A")
    page.get_by_role("button", name="Send back").click()
    page.get_by_role("button", name="Confirm").click()                         # note is required
    expect(page.get_by_label("What needs to change *")).to_be_visible()
    page.get_by_role("button", name="Back").click()
    act(page, "Approve")
    expect(chip(page, "Approved")).to_be_visible()
    page.keyboard.press("Escape")
    page.goto(BASE + "/dpr?tab=summary")
    expect(page.get_by_text(re.compile(r"Slab shuttering"))).to_be_visible()
    download(page)


# ---------------------------------------------------------------- labour & attendance
def test_attendance_marked_approved_and_locked(page: Page):
    sign_in(page, "supervisor")
    page.goto(BASE + "/labour")
    page.get_by_label("Site").first.select_option(label=SITE)
    page.get_by_role("button", name="All present").click()
    page.get_by_role("button", name="Save attendance").click()
    expect(page.get_by_text(re.compile(r"Saved \d+ marks"))).to_be_visible()
    day = page.get_by_label("Date").input_value()
    site_id = page.get_by_label("Site").first.input_value()
    saved = page.request.get(f"{BASE}/api/attendance/?site={site_id}&from={day}&to={day}").json()["count"]
    assert saved >= 8, (day, saved)                                                     # really stored
    assert not page.get_by_role("button", name="Approve this day").is_visible()      # supervisor can't approve
    sign_out(page)
    sign_in(page, "pm")
    page.goto(BASE + "/labour")
    page.get_by_label("Site").first.select_option(label=SITE)
    page.get_by_label("Date").fill(day)
    expect(page.get_by_text(re.compile(r"\b[1-9]\d* present"))).to_be_visible()          # marks loaded
    page.get_by_role("button", name="Approve this day").click()
    expect(page.get_by_text("This day is approved — attendance is locked.")).to_be_visible()
    page.goto(BASE + "/labour?tab=summary")
    expect(page.get_by_text("Wages").first).to_be_visible()
    download(page)


# ---------------------------------------------------------------- expenses & bills
def test_bill_submit_approve_pay_with_controls(page: Page):
    sign_in(page, "accounts")
    page.goto(BASE + "/expenses")
    page.get_by_role("button", name="+ Add bill").click()
    page.get_by_label("Site *").select_option(label=SITE)
    page.get_by_label("Category *").select_option("Transport")
    page.get_by_label("Paid to (supplier / contractor) *").fill("E2E Movers")
    page.get_by_label("Bill / invoice number").fill("E2E-1")
    page.get_by_label("What for *").fill("Shifting shuttering to Tower A")
    page.get_by_label("Amount before GST (₹) *").fill("10000")
    page.get_by_label("GST (₹)", exact=True).fill("1800")
    page.get_by_role("button", name="Save").click()
    act(page, "Submit for approval")
    expect(chip(page, "Waiting approval")).to_be_visible()
    assert not page.get_by_role("button", name="Approve", exact=True).is_visible()   # can't approve own bill
    sign_out(page)

    sign_in(page, "management")
    page.goto(BASE + "/expenses?tab=submitted")
    open_row(page, "E2E Movers")
    page.get_by_role("button", name="Approve", exact=True).click()
    page.get_by_label(re.compile("Amount approved")).fill("11801")
    page.get_by_role("button", name="Confirm").click()
    expect(page.get_by_text("more than the bill")).to_be_visible()
    page.get_by_label(re.compile("Amount approved")).fill("11800")
    page.get_by_role("button", name="Confirm").click()
    expect(chip(page, "Approved — to pay")).to_be_visible()
    assert not page.get_by_role("button", name="Record payment").is_visible()        # management doesn't pay
    page.keyboard.press("Escape")
    # rejection of the demo bill waiting approval needs a reason
    page.goto(BASE + "/expenses?tab=submitted")
    open_row(page, "Balaji Earthmovers")
    act(page, "Reject", {"Why *": "Hours not matching the log book"})
    expect(chip(page, "Rejected")).to_be_visible()
    sign_out(page)

    sign_in(page, "accounts")
    page.goto(BASE + "/expenses?tab=approved,part_paid")
    open_row(page, "E2E Movers")
    page.get_by_role("button", name="Record payment").click()
    page.get_by_label(re.compile("Amount paid")).fill("20000")
    page.get_by_role("button", name="Confirm").click()
    expect(page.get_by_text("still approved for payment")).to_be_visible()
    page.get_by_label(re.compile("Amount paid")).fill("5000")
    page.get_by_label("UTR / cheque number").fill("E2E-UTR-1")
    page.get_by_role("button", name="Confirm").click()
    expect(chip(page, "Part paid")).to_be_visible()
    act(page, "Record payment", {"UTR / cheque number": "E2E-UTR-1"})                # same reference again
    expect(page.get_by_text("already recorded on this bill")).to_be_visible()
    page.get_by_label("UTR / cheque number").fill("E2E-UTR-2")
    page.get_by_role("button", name="Confirm").click()
    expect(chip(page, "Paid")).to_be_visible()
    page.keyboard.press("Escape")
    download(page)
    sign_out(page)
    sign_in(page, "safety")
    page.goto(BASE + "/expenses")
    expect(page.get_by_text(DENIED)).to_be_visible()


# ---------------------------------------------------------------- quality & safety
def test_ncr_closes_only_with_evidence(page: Page, tmp_path):
    sign_in(page, "safety")
    page.goto(BASE + "/quality")
    open_row(page, "DEMO-NCR-001")
    act(page, "Close", {"How it was resolved *": "Repaired and checked"})
    expect(page.get_by_text("needs a closure photo or document")).to_be_visible()
    page.get_by_role("button", name="Back").click()
    sign_out(page)
    sign_in(page, "engineer")
    page.goto(BASE + "/quality")
    open_row(page, "DEMO-NCR-001")
    assert not page.get_by_role("button", name="Close", exact=True).is_visible()     # engineer can't close
    pic = tmp_path / "c4-after-repair.jpg"
    pic.write_bytes(b"\xff\xd8\xff\xe0 e2e jpeg")
    page.get_by_label("Choose file").set_input_files(str(pic))
    page.get_by_label("File is").select_option("evidence")
    page.get_by_role("button", name="Upload").click()
    expect(page.get_by_role("link", name="c4-after-repair.jpg")).to_be_visible()
    sign_out(page)
    sign_in(page, "safety")
    page.goto(BASE + "/quality")
    open_row(page, "DEMO-NCR-001")
    with page.expect_download() as d:
        page.get_by_role("link", name="c4-after-repair.jpg").click()
    assert d.value.suggested_filename == "c4-after-repair.jpg"
    act(page, "Close", {"How it was resolved *": "Repaired with GP2 grout, re-inspected"})
    expect(chip(page, "Closed")).to_be_visible()
    page.keyboard.press("Escape")
    download(page)


# ---------------------------------------------------------------- drawings & documents
def test_new_revision_kept_alongside_old(page: Page, tmp_path):
    sign_in(page, "engineer")
    page.goto(BASE + "/docs")
    open_row(page, "DEMO-TA-STR-101")
    pdf = tmp_path / "slab-r2.pdf"
    pdf.write_bytes(b"%PDF-1.4 e2e revision two")
    page.get_by_label("Revision file").set_input_files(str(pdf))
    page.get_by_label("What changed").fill("Opening for shaft added")
    page.get_by_role("button", name="Upload revision").click()
    expect(page.get_by_role("link", name="slab-r2.pdf")).to_be_visible()
    with page.expect_download() as d:
        page.get_by_role("link", name="DEMO-TA-STR-101-R0.pdf").click()
    with open(d.value.path(), "rb") as f:
        assert f.read().startswith(b"%PDF-1.4 DEMO-TA-STR-101 R0")                   # the old file is untouched
    assert not page.get_by_role("button", name="Archive").is_visible()               # engineer can't archive
    sign_out(page)
    sign_in(page, "qs")
    page.goto(BASE + "/docs")
    expect(page.get_by_text(DENIED)).to_be_visible()


# ---------------------------------------------------------------- plant & equipment
def test_equipment_allocate_breakdown_back_in_service(page: Page):
    sign_in(page, "store")
    page.goto(BASE + "/equipment")
    open_row(page, "DEMO-DG-01")
    page.get_by_role("button", name="Send to a site").click()
    page.get_by_label("Site *").select_option(label=SITE)
    page.get_by_role("button", name="Allocate").click()
    expect(chip(page, "In use")).to_be_visible()
    page.get_by_role("button", name="Log service / repair / breakdown").click()
    page.get_by_label("Type *").select_option("breakdown")
    page.get_by_label("What was done / what failed *").fill("Alternator fault")
    page.get_by_label("Downtime (hours)").fill("5")
    page.get_by_role("button", name="Confirm").click()
    expect(chip(page, "Breakdown")).to_be_visible()
    act(page, "Back in service")
    expect(chip(page, "In use")).to_be_visible()
    page.keyboard.press("Escape")
    page.goto(BASE + "/equipment?tab=utilisation")
    expect(page.locator("table tbody tr", has_text="DEMO-DG-01").first).to_be_visible()


# ---------------------------------------------------------------- indents step 11 (money control in the browser)
def test_invoice_mismatch_needs_reason(page: Page):
    sign_in(page, "accounts")
    rows = page.request.get(BASE + "/api/indents/?tab=purchases").json()["results"]
    target = next(i for i in rows if "Shaft walls" in (i.get("purpose") or "") or i["pstage"] == "invoice")
    page.goto(f"{BASE}/indents/{target['id']}")
    page.get_by_role("button", name="Invoice verified").click()
    page.get_by_label("Invoice number").fill("E2E-INV-9")
    page.get_by_label("Invoice amount before GST (₹)").fill("999")
    page.get_by_role("button", name="Confirm").click()
    expect(page.get_by_text("differs from PO rate")).to_be_visible()
    page.get_by_label(re.compile("^Remarks")).fill("Part invoice agreed with supplier")
    page.get_by_role("button", name="Confirm").click()
    expect(page.get_by_text("Invoice Verified").first).to_be_visible()


# ---------------------------------------------------------------- reports
def test_reports_by_role_and_export(page: Page):
    sign_in(page, "management")
    page.goto(BASE + "/reports")
    for section in ["Indents & purchase", "Expenses & bills", "Labour & attendance", "Quality & safety", "Plant & equipment"]:
        expect(page.get_by_role("heading", name=section)).to_be_visible()
    expect(page.locator("table", has_text="[Demo] Tower A").first).to_be_visible()
    download(page)
    sign_out(page)
    sign_in(page, "qs")
    page.goto(BASE + "/reports")
    expect(page.get_by_role("heading", name="Expenses & bills")).to_be_visible()
    expect(page.get_by_role("heading", name="Labour & attendance")).to_have_count(0)    # QS can't see labour


def tiny_png() -> bytes:
    """A valid 2×2 PNG, built here so the test needs no image file."""
    import struct
    import zlib

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    raw = b"".join(b"\x00" + b"\xb8\x89\x2b" * 2 for _ in range(2))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


# ---------------------------------------------------------------- dashboard & materials
def test_dashboard_cards_follow_role(page: Page):
    sign_in(page, "management")
    expect(page.get_by_text("Bills to approve")).to_be_visible()
    expect(page.get_by_text("Open quality & safety items")).to_be_visible()
    sign_out(page)
    sign_in(page, "safety")
    expect(page.get_by_text("Open quality & safety items")).to_be_visible()
    expect(page.get_by_text("Bills to approve")).to_have_count(0)                      # no finance for safety


def test_materials_catalogue_and_stock_export(page: Page):
    sign_in(page, "store")
    page.goto(BASE + "/materials?tab=catalogue")
    expect(page.get_by_text("[Demo] OPC 53 cement").first).to_be_visible()
    download(page)
    sign_out(page)
    sign_in(page, "safety")
    page.goto(BASE + "/materials")
    expect(page.get_by_text(DENIED)).to_be_visible()

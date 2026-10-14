"""Browser tests (Chromium via Playwright) against the production build + Django on a CI-only database.

Each role signs in through the real login form; the sidebar, direct URLs and one workflow step are checked.
"""
import os
import re

import pytest
from playwright.sync_api import Page, expect

BASE = os.environ.get("E2E_BASE", "http://localhost:4173")
PW = os.environ["E2E_PASSWORD"]
MOBILE = {k: f"95000000{n:02d}" for n, k in enumerate(
    ["admin", "management", "pm", "purchase", "accounts", "qs", "safety", "engineer", "supervisor", "store"])}

LABEL = {"dashboard": "Dashboard", "reports": "Reports", "sites": "Sites & Projects", "tasks": "Tasks & Schedule",
         "dpr": "Daily Progress", "labour": "Labour & Attendance", "materials": "Materials & Stock",
         "indents": "Indents & Purchase", "equipment": "Plant & Equipment", "expenses": "Expenses & Bills",
         "quality": "Quality & Safety", "docs": "Drawings & Documents", "team": "Team & Roles", "settings": "Settings"}
PATH = {"reports": "/reports", "sites": "/sites", "tasks": "/tasks", "dpr": "/dpr", "labour": "/labour",
        "materials": "/materials", "indents": "/indents", "equipment": "/equipment", "expenses": "/expenses",
        "quality": "/quality", "docs": "/docs", "team": "/team", "settings": "/settings"}
WORK = ["dashboard", "reports", "sites", "tasks", "dpr", "labour", "materials", "indents", "equipment", "expenses",
        "quality", "docs"]
# what each role should see — from the role table in backend/apps/accounts/roles.py
VIEW = {
    "admin": WORK + ["team", "settings"], "management": WORK, "pm": WORK,
    "purchase": ["dashboard", "reports", "sites", "materials", "indents", "expenses"],
    "accounts": ["dashboard", "reports", "sites", "expenses", "labour", "materials", "indents"],
    "qs": ["dashboard", "reports", "sites", "materials", "indents", "expenses"],
    "safety": ["dashboard", "quality", "dpr", "labour", "docs"],
    "engineer": ["dashboard", "reports", "sites", "tasks", "dpr", "labour", "materials", "indents", "equipment", "quality", "docs"],
    "supervisor": ["dashboard", "tasks", "dpr", "labour", "materials", "indents", "equipment", "quality"],
    "store": ["dashboard", "materials", "indents", "equipment", "dpr"],
}
CAN_RAISE = {"admin", "management", "pm", "purchase", "accounts", "engineer", "supervisor", "store"}
EXPECT = {k: ({LABEL[m] for m in v}, k in CAN_RAISE) for k, v in VIEW.items()}
DENIED = "You don’t have access to this page"


def sign_in(page: Page, role: str):
    page.goto(f"{BASE}/login")
    page.get_by_label("Mobile number").fill(MOBILE[role])
    page.get_by_label("Password").fill(PW)
    expect(page.get_by_label("Mobile number")).to_have_value(MOBILE[role])
    with page.expect_response(lambda r: "/api/auth/login/" in r.url) as resp:
        page.get_by_role("button", name="Sign in").click()
    r = resp.value
    assert r.status == 200, (role, r.status, r.text()[:300])
    expect(page.get_by_text(re.compile(r"Good day"))).to_be_visible(timeout=15_000)


def sign_out(page: Page):
    page.wait_for_load_state("networkidle")
    if page.locator("[role=dialog]").count():           # close an open window (it covers the header)
        page.get_by_role("button", name="Close window").first.click()
    expect(page.locator("[role=dialog]")).to_have_count(0)
    page.get_by_role("button", name="Log out").click()
    expect(page.get_by_role("button", name="Sign in")).to_be_visible()


def sidebar(page: Page) -> set[str]:
    return {t.strip() for t in page.locator("aside nav a span:first-child").all_inner_texts()}


@pytest.mark.parametrize("role", list(EXPECT))
def test_role_sidebar_and_direct_urls(page: Page, role):
    nav, can_raise = EXPECT[role]
    sign_in(page, role)
    assert sidebar(page) == nav, (role, sidebar(page))
    for module, path in PATH.items():
        page.goto(BASE + path)
        page.wait_for_load_state("networkidle")
        denied = page.get_by_text(DENIED).is_visible()
        assert denied == (module not in VIEW[role]), (role, path, "denied" if denied else "shown")
    page.goto(BASE + "/indents/new")
    page.wait_for_load_state("networkidle")
    assert page.get_by_text(DENIED).is_visible() == (not can_raise), (role, "/indents/new")
    sign_out(page)
    page.goto(BASE + "/indents")
    expect(page.get_by_role("button", name="Sign in")).to_be_visible()      # signed out → back to login


def test_raise_indent_and_stock_check_in_the_browser(page: Page):
    sign_in(page, "engineer")
    page.goto(BASE + "/indents/new")
    page.locator("select").first.select_option(label="E2E — E2E Test Site")
    page.get_by_placeholder("e.g. Shuttering oil").fill("E2E binding wire")
    page.get_by_placeholder("bag, cum, kg, nos").fill("kg")
    page.locator("input[type=number]").first.fill("25")
    page.get_by_role("button", name="Raise indent").click()
    expect(page.get_by_role("heading", name=re.compile(r"IND-.* · E2E binding wire"))).to_be_visible()
    url = page.url
    sign_out(page)

    sign_in(page, "pm")                        # Project Head acts at 03, not at the 02 stock check
    page.goto(url)
    expect(page.get_by_role("heading", name=re.compile("E2E binding wire"))).to_be_visible()
    assert not page.get_by_text("Your action").is_visible()
    sign_out(page)

    sign_in(page, "store")
    page.goto(url)
    page.get_by_role("button", name="Verified — forward").click()
    page.get_by_role("button", name="Confirm").click()
    expect(page.locator("span.chip", has_text="Under Verification").first).to_be_visible()
    expect(page.get_by_text("Approved", exact=False).first).to_be_visible()
    sign_out(page)


def test_phone_width_has_no_sideways_scroll(page: Page):
    page.set_viewport_size({"width": 390, "height": 844})
    sign_in(page, "admin")
    for path in ["/", *PATH.values()]:
        page.goto(BASE + path)
        page.wait_for_load_state("networkidle")
        sw, iw = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
        assert sw <= iw + 1, (path, sw, iw)


def test_daily_report_written_submitted_and_approved_in_the_browser(page: Page):
    sign_in(page, "engineer")
    page.goto(BASE + "/dpr")
    page.get_by_role("button", name="+ Today's report").click()
    page.get_by_label("Site *").select_option(label="E2E Test Site")
    page.get_by_label("Work done today").fill("E2E: plinth beam shuttering")
    page.get_by_placeholder("Activity").first.fill("Shuttering")
    page.get_by_placeholder("Qty").first.fill("85")
    page.get_by_placeholder("Unit").first.fill("sqm")
    page.get_by_role("button", name="Save draft").click()
    expect(page.get_by_text("E2E: plinth beam shuttering").first).to_be_visible()
    page.get_by_role("button", name="Submit for approval").click()
    page.get_by_role("button", name="Confirm").click()
    expect(page.locator("span.chip", has_text="Waiting approval").first).to_be_visible()
    url = page.url
    sign_out(page)

    sign_in(page, "store")                      # store keeper can read reports but not approve
    page.goto(url)
    expect(page.get_by_text("E2E: plinth beam shuttering").first).to_be_visible()
    assert not page.get_by_role("button", name="Approve", exact=True).is_visible()
    sign_out(page)

    sign_in(page, "pm")
    page.goto(url)
    page.get_by_role("button", name="Approve", exact=True).click()
    page.get_by_role("button", name="Confirm").click()
    expect(page.locator("span.chip", has_text="Approved").first).to_be_visible()

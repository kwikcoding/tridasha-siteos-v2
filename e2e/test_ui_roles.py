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

D, M, I, T, S = "Dashboard", "Materials & Stock", "Indents & Purchase", "Team & Roles", "Settings"
# what each role should see — from the role table in backend/apps/accounts/roles.py
EXPECT = {
    "admin": ({D, M, I, T, S}, True), "management": ({D, M, I}, True), "pm": ({D, M, I}, True),
    "purchase": ({D, M, I}, True), "accounts": ({D, M, I}, True), "qs": ({D, M, I}, False),
    "safety": ({D}, False), "engineer": ({D, M, I}, True), "supervisor": ({D, M, I}, True), "store": ({D, M, I}, True),
}
DENIED = "You don’t have access to this page"


def sign_in(page: Page, role: str):
    page.goto(f"{BASE}/login")
    page.get_by_label("Mobile number").fill(MOBILE[role])
    page.get_by_label("Password").fill(PW)
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_text(re.compile(r"Good day"))).to_be_visible(timeout=15_000)


def sign_out(page: Page):
    page.get_by_role("button", name="Log out").click()
    expect(page.get_by_role("button", name="Sign in")).to_be_visible()


def sidebar(page: Page) -> set[str]:
    return {t.strip() for t in page.locator("aside nav a span:first-child").all_inner_texts()}


@pytest.mark.parametrize("role", list(EXPECT))
def test_role_sidebar_and_direct_urls(page: Page, role):
    nav, can_raise = EXPECT[role]
    sign_in(page, role)
    assert sidebar(page) == nav, (role, sidebar(page))
    for path, label in [("/team", T), ("/settings", S), ("/materials", M), ("/indents", I)]:
        page.goto(BASE + path)
        page.wait_for_load_state("networkidle")
        denied = page.get_by_text(DENIED).is_visible()
        assert denied == (label not in nav), (role, path, "denied" if denied else "shown")
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
    for path in ["/", "/indents", "/materials", "/team", "/settings"]:
        page.goto(BASE + path)
        page.wait_for_load_state("networkidle")
        sw, iw = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
        assert sw <= iw + 1, (path, sw, iw)

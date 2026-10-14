"""Browser tests for Materials & Stock and Team & Roles (on the CI database with demo data)."""
import io
import os
import re

from playwright.sync_api import Page, expect

from test_modules_ui import BASE, DEMO, DENIED, PW, chip, download, sign_in, sign_out

STOCK_SITE = "DEMO — Demo site (try-out data)"


def material_pick(page: Page, text: str, pick: str):
    page.get_by_label("Search the catalogue").fill(text)
    page.get_by_role("button", name=re.compile(pick)).first.click()


# ---------------------------------------------------------------- materials & stock
def test_stock_entries_no_negative_and_adjustment_needs_reason(page: Page):
    sign_in(page, "store")
    page.goto(BASE + "/materials?tab=stock")
    page.get_by_label("Site", exact=True).select_option(label=STOCK_SITE)
    page.get_by_role("button", name="+ Stock entry").click()
    material_pick(page, "DEMO-SAND", "DEMO-SAND")
    page.get_by_label("Type").select_option("OUT")
    page.get_by_label("Quantity").fill("9999")
    page.get_by_role("button", name="Save entry").click()
    expect(page.get_by_text(re.compile(r"Only .* in stock"))).to_be_visible()        # can't go below zero
    page.get_by_label("Quantity").fill("2")
    page.get_by_label("Ref (GRN / challan)").fill("E2E-ISS-1")
    page.get_by_role("button", name="Save entry").click()
    expect(page.locator("[role=dialog]")).to_have_count(0)
    # an adjustment needs a reason (the browser refuses to submit without it)
    page.get_by_role("button", name="+ Stock entry").click()
    material_pick(page, "DEMO-SAND", "DEMO-SAND")
    page.get_by_label("Type").select_option("ADJ")
    page.get_by_label(re.compile("^Quantity")).fill("-1")
    page.get_by_role("button", name="Save entry").click()
    expect(page.locator("[role=dialog]")).to_be_visible()
    page.get_by_label(re.compile("^Note")).fill("E2E physical count")
    page.get_by_role("button", name="Save entry").click()
    expect(page.locator("[role=dialog]")).to_have_count(0)
    page.get_by_role("button", name="Ledger").click()
    expect(page.get_by_text("E2E-ISS-1")).to_be_visible()
    expect(page.get_by_text("E2E physical count")).to_be_visible()
    download(page)
    sign_out(page)
    sign_in(page, "engineer")                                  # engineer sees stock but can't post it
    page.goto(BASE + "/materials?tab=stock")
    expect(page.get_by_role("button", name="Ledger")).to_be_visible()
    assert page.get_by_role("button", name="+ Stock entry").count() == 0


def test_catalogue_add_edit_and_excel_upload_preview(page: Page, tmp_path):
    from openpyxl import Workbook
    sign_in(page, "store")
    page.goto(BASE + "/materials?tab=catalogue")
    page.get_by_role("button", name="+ Add material").click()
    for label, value in [("Code", "E2E-BW"), ("Name", "E2E binding wire 18g"), ("Category", "Steel"), ("Unit", "kg"),
                         ("Standard rate (₹)", "78")]:
        page.get_by_label(label, exact=True).fill(value)
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page.locator("table tbody tr", has_text="E2E-BW").first).to_be_visible()
    # upload: preview first, nothing changes until confirmed
    wb = Workbook()
    ws = wb.active
    ws.append(["Code", "Name", "Category", "Unit", "Rate"])
    ws.append(["E2E-UP-1", "E2E uploaded item one", "Hardware", "nos", 12])
    ws.append(["E2E-BW", "E2E binding wire 18g (updated)", "Steel", "kg", 80])
    ws.append(["", "row with no code", "", "", ""])
    path = tmp_path / "catalogue.xlsx"
    wb.save(path)
    page.get_by_role("button", name="Upload Excel / CSV").click()
    page.get_by_label("Spreadsheet file").set_input_files(str(path))
    page.get_by_role("button", name="Check file").click()
    expect(page.get_by_role("button", name="Import 2 row(s)")).to_be_visible()
    page.get_by_role("button", name="Import 2 row(s)").click()
    expect(page.get_by_text(re.compile(r"Imported: 1 new, 1 updated"))).to_be_visible()
    page.get_by_role("button", name="Done").click()
    expect(page.locator("table tbody tr", has_text="E2E-UP-1").first).to_be_visible()
    expect(page.get_by_text("E2E binding wire 18g (updated)")).to_be_visible()
    sign_out(page)
    sign_in(page, "purchase")                                   # purchase can view, not upload or add
    page.goto(BASE + "/materials?tab=catalogue")
    expect(page.locator("table tbody tr", has_text="E2E-BW").first).to_be_visible()
    assert page.get_by_role("button", name="Upload Excel / CSV").count() == 0
    assert page.get_by_role("button", name="+ Add material").count() == 0


# ---------------------------------------------------------------- team & roles
def test_admin_creates_login_forced_password_change_then_deactivates(page: Page):
    new_mobile, temp = "9555500001", PW + "-t1"
    sign_in(page, "admin")
    page.goto(BASE + "/team?tab=departments")
    page.get_by_label("Name", exact=True).fill("E2E Stores")
    page.get_by_role("button", name="Add department").click()
    expect(page.get_by_text("E2E Stores").first).to_be_visible()
    page.goto(BASE + "/team?tab=people")
    page.get_by_role("button", name="+ Add person").click()
    page.get_by_label("Full name").fill("E2E New Store Assistant")
    page.get_by_label("Mobile (login)").fill(new_mobile)
    page.get_by_label("Employee ID").fill("E2E-042")
    page.get_by_label("Designation").fill("Store Assistant")
    page.get_by_label("Department").select_option(label="E2E Stores")
    page.get_by_label("Main role").select_option(label="Store Keeper")
    page.get_by_label(re.compile("DEMO — Demo site")).check()
    page.get_by_label("Temporary password").fill(temp)
    page.get_by_role("button", name="Create login").click()
    row = page.locator("table tbody tr", has_text="E2E New Store Assistant")
    expect(row).to_contain_text("temp password")
    expect(row).to_contain_text("Store Keeper")
    sign_out(page)

    # first sign-in: must set an own password before anything else
    page.goto(f"{BASE}/login")
    page.get_by_label("Mobile number").fill(new_mobile)
    page.get_by_label("Password").fill(temp)
    page.get_by_role("button", name="Sign in").click()
    expect(page).to_have_url(re.compile(r"/profile$"))
    page.goto(BASE + "/indents")
    expect(page).to_have_url(re.compile(r"/profile$"))                            # can't go anywhere else yet
    page.get_by_label("Current password").fill(temp)
    page.get_by_label("New password", exact=True).fill(PW + "-own")
    page.get_by_label("Repeat new password").fill(PW + "-own")
    page.get_by_role("button", name="Change password").click()
    page.goto(BASE + "/")
    expect(page.get_by_text(re.compile("Good day"))).to_be_visible()
    expect(page.locator("aside nav")).to_contain_text("Materials & Stock")
    expect(page.locator("aside nav")).not_to_contain_text("Team & Roles")
    page.goto(BASE + "/team")
    expect(page.get_by_text(DENIED)).to_be_visible()
    sign_out(page)

    # deactivate: the person can no longer sign in
    sign_in(page, "admin")
    page.goto(BASE + "/team?tab=people")
    page.locator("table tbody tr", has_text="E2E New Store Assistant").get_by_role("button", name="Edit").click()
    page.get_by_label("Login active").uncheck()
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page.locator("table tbody tr", has_text="E2E New Store Assistant")).to_contain_text("Off")
    page.goto(BASE + "/team?tab=audit")
    expect(page.get_by_text(re.compile("E2E New Store Assistant")).first).to_be_visible()
    sign_out(page)
    page.goto(f"{BASE}/login")
    page.get_by_label("Mobile number").fill(new_mobile)
    page.get_by_label("Password").fill(PW + "-own")
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_text("Wrong mobile number or password.")).to_be_visible()


def test_permission_matrix_change_takes_effect_and_is_reverted(page: Page):
    def set_store_reports(on: bool):
        sign_in(page, "admin")
        page.goto(BASE + "/team?tab=matrix")
        page.get_by_role("button", name="Overview", exact=True).click()
        box = page.get_by_label("Store Keeper: Reports View")
        box.check() if on else box.uncheck()
        page.get_by_role("button", name=re.compile(r"^Save")).click()
        expect(page.get_by_role("button", name=re.compile(r"^Save"))).to_be_disabled()
        sign_out(page)
    sign_in(page, "store")
    page.goto(BASE + "/reports")
    expect(page.get_by_text(DENIED)).to_be_visible()
    sign_out(page)
    set_store_reports(True)
    sign_in(page, "store")
    expect(page.locator("aside nav")).to_contain_text("Reports")
    page.goto(BASE + "/reports")
    expect(page.get_by_role("heading", name="Reports")).to_be_visible()
    sign_out(page)
    set_store_reports(False)                                   # put the demo role back as it was
    sign_in(page, "store")
    page.goto(BASE + "/reports")
    expect(page.get_by_text(DENIED)).to_be_visible()


def test_non_admin_cannot_reach_team_api_even_directly(page: Page):
    sign_in(page, "management")
    for url in ["/api/users/", "/api/audit/", "/api/departments/"]:
        r = page.request.get(BASE + url)
        assert r.status in (403, 200), url
        if url != "/api/departments/":
            assert r.status == 403, (url, r.status)
    r = page.request.patch(BASE + "/api/roles/1/", data={"label": "hack"})
    assert r.status == 403, r.status                            # also refused without a CSRF token

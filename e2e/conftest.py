"""On a failed browser test, print where the page was and what it showed (CI can't keep screenshots)."""
import pytest


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call" and rep.failed:
        page = item.funcargs.get("page")
        if page is not None:
            try:
                text = page.inner_text("body")[:1200].replace("\n", " | ")
                print(f"\nPAGE-URL: {page.url}\nPAGE-TEXT: {text}\nPAGE-DIALOGS: {page.locator('[role=dialog]').count()}")
            except Exception as e:                     # page may be closed
                print(f"\nPAGE-URL: unavailable ({e})")

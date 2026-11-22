"""Opens the generated report in a real Chromium/Chrome (skipped when Playwright or a browser is unavailable)."""
import shutil

import pytest

pw = pytest.importorskip("playwright.sync_api")
CHROME = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium binary")
def test_report_renders_without_errors(js_repo, run_ct):
    run_ct(js_repo, "scan", "--quiet")
    run_ct(js_repo, "trace", "POST /api/auth/login")
    run_ct(js_repo, "context", "signToken")
    r = run_ct(js_repo, "report")
    url = "file://" + r["index_html"]
    errors = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME)
        pg = b.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        for tab in ("overview", "architecture", "flows", "code", "learn", "contribute", "changes", "simulation"):
            pg.goto(url + "#/" + tab)
            pg.wait_for_timeout(250)
            assert pg.inner_text("main h1")
        pg.goto(url + "#/flows")
        pg.click("#p-next")
        pg.click("#p-next")
        assert pg.inner_text("#p-count").startswith("Step 3")
        assert "auth.controller.js" in pg.inner_text("#step-code") or "auth.routes.js" in pg.inner_text("#step-code")
        pg.select_option("#lang-select", "hi")
        assert "कदम" in pg.inner_text("#p-count")
        pg.goto(url + "#/code/src%2Fcontrollers%2Fauth.controller.js:14-17")
        pg.wait_for_timeout(200)
        assert pg.locator("#codeview .ln.hl").count() == 4
        pg.goto(url + "#/architecture")
        pg.wait_for_timeout(600)
        assert pg.locator("#cy canvas").count() > 0
        b.close()
    assert errors == []

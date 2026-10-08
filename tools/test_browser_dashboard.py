"""End-to-end browser checks for actual model-backed interactive dashboard.

Uses installed Playwright + local Chrome; no user data or remote browser.
"""
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/"docs"
GRID=json.loads((DOCS/"data"/"assumption_grid.json").read_text(encoding="utf-8"))
LOOKUP={x["key"]:x for x in GRID["cases"]}

class Quiet(SimpleHTTPRequestHandler):
    def log_message(self,*args):
        pass

server=ThreadingHTTPServer(("127.0.0.1",0),partial(Quiet,directory=str(DOCS)))
thread=threading.Thread(target=server.serve_forever,daemon=True)
thread.start()
try:
    with sync_playwright() as pl:
        chrome=Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
        # The project owner has local Chrome on Windows. Other environments
        # can use a Playwright-provisioned Chromium browser.
        options={"headless":True,"args":["--no-sandbox"]}
        if chrome.is_file():
            options["executable_path"]=str(chrome)
        browser=pl.chromium.launch(**options)
        page=browser.new_page(viewport={"width":1480,"height":930},device_scale_factor=1)
        errors=[]
        page.on("pageerror",lambda e:errors.append(str(e)))
        page.goto("http://127.0.0.1:"+str(server.server_port)+"/",
                  wait_until="networkidle",timeout=35000)
        page.locator("#comparisonBody tr").first.wait_for(timeout=12000)
        assert page.locator("#countrySelect").input_value()=="CA"
        assert page.locator("#scenarioSelect option").count()==6
        assert page.locator("#pmCostBridge .bridge-row").count()==4
        assert page.locator("#weightsChart .bar-post").count()==4
        assert "Canadian" in page.locator("#taxBasisHeading").inner_text()
        assert "C$" in page.locator("#pmAdvantage").inner_text()
        print("BROWSER_INITIAL_CANADA_PASS")

        # TE constraint change from independently reoptimized file.
        page.locator("#teInput").select_option("0.012")
        assert page.locator("#kTE").inner_text()=="1.20%"
        expected=next(m for m in LOOKUP["CA:0:0.012:10:0.8:0.2"]["methods"]
                 if m["method"]=="two_stage_convex_heuristic")
        actual=page.locator("#decisionTotals").inner_text()
        assert f"{abs(expected['objective_dollars']):,.2f}" in actual,(expected,actual)
        print("BROWSER_RISK_SLIDER_ACTUAL_SOLVER_PASS",expected["objective_dollars"])

        # Fee and loss usability both really recalculate recommendation.
        page.locator("#feeInput").select_option("40")
        page.locator("#lossInput").select_option("0.2")
        expected=next(m for m in LOOKUP["CA:0:0.012:40:0.2:0.2"]["methods"]
                 if m["method"]=="two_stage_convex_heuristic")
        actual=page.locator("#decisionTotals").inner_text()
        assert f"{abs(expected['objective_dollars']):,.2f}" in actual,(expected,actual)
        assert page.locator("#comparisonBody tr").count()==5
        print("BROWSER_FEE_LOSS_CHANGES_PASS",expected["objective_dollars"])

        page.locator("#futureInput").select_option("0")
        expected=next(m for m in LOOKUP["CA:0:0.012:40:0.2:0.0"]["methods"]
                 if m["method"]=="two_stage_convex_heuristic")
        assert f"{abs(expected['objective_dollars']):,.2f}" in page.locator("#decisionTotals").inner_text()
        print("BROWSER_FUTURE_RECAPTURE_ACTUAL_SOLVER_PASS",expected["objective_dollars"])
        page.locator("#futureInput").select_option("0.2")

        # Canadian affiliated-case data and 30-day review.
        page.locator("#scenarioSelect").select_option(
            label="Canada / Affiliated recent purchase")
        assert page.locator("#taxLotBody .tag-flag").count()>=1
        assert "Recent purchase" in page.locator("#taxLotBody .tag-flag").first.inner_text()
        print("BROWSER_CANADA_AFFILIATE_FLAG_PASS")

        # Decision method switching updates three bars per ETF and PM summary.
        page.locator("#methodSelect").select_option("risk_only_rebalance")
        assert page.locator("#weightsChart .bar-post").count()==4
        assert page.locator("#pmCostBridge .bridge-row").count()==4
        assert "0.00" in page.locator("#pmAdvantage").inner_text()
        page.locator("#resetAssumptions").click()
        assert page.locator("#teInput").input_value()=="0.025"
        assert page.locator("#feeInput").input_value()=="10"
        assert page.locator("#lossInput").input_value()=="0.8"
        assert page.locator("#futureInput").input_value()=="0.2"
        print("BROWSER_METHOD_SELECTION_RESET_PASS")

        page.locator("#countrySelect").select_option("US")
        assert page.locator("#scenarioSelect option").count()==5
        assert "U.S." in page.locator("#taxBasisHeading").inner_text()
        page.locator("#methodSelect").select_option("two_stage_convex_heuristic")
        assert "US$" in page.locator("#pmAdvantage").inner_text()
        page.locator("#feeInput").select_option("5")
        expected=next(m for m in LOOKUP["US:0:0.025:5:0.8:0.2"]["methods"]
                 if m["method"]=="two_stage_convex_heuristic")
        assert f"{abs(expected['objective_dollars']):,.2f}" in page.locator("#decisionTotals").inner_text()
        print("BROWSER_US_SOLVER_SWITCH_PASS",expected["objective_dollars"])

        screenshots=ROOT/"runs"/"browser_qa"
        screenshots.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(screenshots/"desktop.png"),full_page=True)
        page.set_viewport_size({"width":390,"height":844})
        page.locator("#countrySelect").select_option("CA")
        assert page.locator(".pm-summary").count()==1
        assert page.locator("#pmCostBridge .bridge-row").count()==4
        overflow=page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        assert overflow<=3, f"Mobile horizontal page overflow {overflow}px"
        page.screenshot(path=str(screenshots/"mobile.png"),full_page=True)
        print("BROWSER_MOBILE_PASS_NO_OVERFLOW")
        assert not errors, errors
        browser.close()
    print("BROWSER_PM_END_TO_END_PASS")
finally:
    server.shutdown()
    server.server_close()

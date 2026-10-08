"""Static website integrity and HTTP smoke tests, no browser dependencies.

Test the real HTML IDs, references in JavaScript, actual generated JSON,
jurisdiction routing source, and local HTTP endpoints. This does not replace
a fully interactive browser regression run.
"""
from html.parser import HTMLParser
from pathlib import Path
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from threading import Thread
import re
import urllib.request
import json

ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/"docs"

class IDParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids=set()
    def handle_starttag(self,tag,attrs):
        props=dict(attrs)
        if props.get("id"):
            self.ids.add(props["id"])

html=(DOCS/"index.html").read_text(encoding="utf-8")
js=(DOCS/"app.js").read_text(encoding="utf-8")
parser=IDParser();parser.feed(html)
used=set(re.findall(r'el\("([^"]+)"\)',js))
missing=sorted(used-parser.ids)
print("HTML_IDS",len(parser.ids),"JS_IDS",len(used),"MISSING",missing)
assert len(parser.ids)>20 and len(used)>20 and not missing
for required in ("countrySelect","scenarioSelect","jurisdictionWarning",
    "taxBasisHeading","kEquity","comparisonBody","tradeBody","frontierChart"):
    assert required in parser.ids
assert "populate(\"CA\")" in js
assert "s.currency" in js and "CAD" in js and "USD" in js
assert "canada" in js.lower()

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,*args):
        pass

server=ThreadingHTTPServer(("127.0.0.1",0),partial(QuietHandler,directory=str(DOCS)))
thread=Thread(target=server.serve_forever,daemon=True);thread.start()
try:
    host="http://127.0.0.1:"+str(server.server_port)
    for route in ("/","/app.js","/styles.css","/data/scenarios.json"):
        with urllib.request.urlopen(host+route,timeout=8) as reply:
            payload=reply.read()
            assert reply.status==200 and len(payload)>300, route
            print("HTTP_200",route,"BYTES",len(payload))
    data=json.loads(urllib.request.urlopen(host+"/data/scenarios.json",timeout=8).read())
    ca=[x for x in data["cases"] if x["currency"]=="CAD"]
    us=[x for x in data["cases"] if x["currency"]=="USD"]
    assert len(ca)==6 and len(us)==5 and data["cases"][0]["currency"]=="CAD"
    assert ca[0]["tax_basis_method"].startswith("Canadian")
    assert ca[0]["tax_lots"][0]["lot_id"]=="ACB-XIC"
    assert any(x["superficial_loss_watch"]["lookback_30d_flagged_tickers"]
               for x in ca)
    print("CA_FIRST_HTTP_DATA_PASS",len(ca),"CASES","US",len(us),"CASES")
finally:
    server.shutdown();server.server_close()
print("STATIC_SITE_VALIDATION_PASS")

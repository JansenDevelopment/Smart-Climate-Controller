#!/usr/bin/env python
"""Local server for the card preview viewer.

    python tools/card-preview/serve.py            # http://localhost:8777/tools/card-preview/viewer.html

Serves the repository root statically (so the viewer can load the real card JS
from custom_components/smart_climate/) and exposes the offline simulation:

    GET /api/scenarios
    GET /api/simulate?name=hot_day&cooling_mode=off&support_enabled=false&hvac_mode=off
                      &support_delta=2&support_grace=15&support_min_rise=0.3
                      &warm_threshold=22&hard_ceiling=26&hysteresis=0.5&devices=airco%2Bcv

The viewer calls /api/simulate again whenever you change a setting on a card
(cooling mode, CV support, power), so the card drives the simulation.
"""

import argparse
import dataclasses
import http.server
import json
import pathlib
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import simulate  # noqa: E402

BOOL = {"support_enabled", "forecast"}
FLOAT = {"support_delta", "support_grace", "support_min_rise", "warm_threshold", "hard_ceiling", "hysteresis"}
STR = {"cooling_mode", "hvac_mode", "devices"}


def run(name: str, params: dict) -> dict:
    scs = simulate.scenarios()
    if name not in scs:
        raise KeyError(name)
    changes = {}
    control = {}
    for key, values in params.items():
        v = values[0]
        if key.startswith("ctl_"):  # ctl_cv=off&ctl_cv_from=ISO&ctl_cv_until=ISO
            kind, _, part = key[4:].partition("_")
            entry = control.setdefault(kind, {"mode": "auto", "from": None, "until": None})
            entry["mode" if not part else part] = v or None
            continue
        if key in BOOL:
            changes[key] = v.lower() in ("1", "true", "yes", "on")
        elif key in FLOAT:
            changes[key] = float(v)
        elif key in STR:
            changes[key] = v
    if control:
        changes["device_control"] = {
            k: (e["mode"], e["from"], e["until"]) for k, e in control.items() if e["mode"] != "auto"
        }
    sc = dataclasses.replace(scs[name], **changes)
    result = simulate.simulate(sc)
    tmp = ROOT / "tools" / "card-preview" / ".last-sim.json"
    simulate.export_json([result], str(tmp))
    data = json.loads(tmp.read_text(encoding="utf-8"))
    tmp.unlink(missing_ok=True)
    out = data["scenarios"][0]
    out["schedule"] = data["schedule"]
    return out


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 - stdlib API
        url = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(url.query)
        if url.path == "/api/scenarios":
            return self._json([
                {"name": k, "title": v.title, "notes": v.notes, "days": v.days}
                for k, v in simulate.scenarios().items()
            ])
        if url.path == "/api/simulate":
            try:
                name = q.pop("name", [""])[0]
                return self._json(run(name, q))
            except KeyError as err:
                return self._json({"error": f"unknown scenario {err}"}, 404)
            except Exception as err:  # noqa: BLE001
                return self._json({"error": str(err)}, 500)
        return super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        if "/api/" not in (args[0] if args else ""):
            return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8777)
    args = ap.parse_args()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Card preview: http://localhost:{args.port}/tools/card-preview/viewer.html")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

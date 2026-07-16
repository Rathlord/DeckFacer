#!/usr/bin/env python3
"""
gui_server.py
=============
A tiny local web server (stdlib only -- http.server, no Flask/etc.) that backs
the browser GUI for archidekt_deck_cards.py.

Why a local server at all, instead of a static page: Archidekt's API blocks
cross-origin browser reads (see CLAUDE.md), so a page opened directly from
disk (or hosted elsewhere) can't fetch deck JSON. This server fetches decks
server-side with urllib (exactly like the CLI does) and hands JSON to the
page over same-origin requests, which sidesteps CORS entirely.

The GUI's live preview reuses render_card()/card_css()/cropmarks_html() from
archidekt_deck_cards.py directly, so what you see in the browser is built
from the exact same code that produces the printed file -- not a lookalike.
"""

import json
import os
import re
import time
import urllib.error
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import archidekt_deck_cards as core

GUI_DIR = Path(__file__).resolve().parent / "gui"

STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
}

OUTPUT_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+\.html$")

# Deck-info cache, keyed by deck id, so toggling a flag re-renders instantly
# instead of re-fetching from Archidekt.
_CACHE = {}
_LAST_FETCH = 0.0
_MIN_INTERVAL = 0.4  # be polite to Archidekt's API, same pace as the CLI


def _throttle():
    global _LAST_FETCH
    wait = _MIN_INTERVAL - (time.monotonic() - _LAST_FETCH)
    if wait > 0:
        time.sleep(wait)
    _LAST_FETCH = time.monotonic()


def _resolve(token, flags=None, use_cache=True):
    did = core.parse_deck_id(token)
    if not did:
        return {"ok": False, "token": token, "error": "Couldn't find a deck ID in that."}
    try:
        if not (use_cache and did in _CACHE):
            _throttle()
            deck = core.fetch_json(core.API_DECK.format(id=did))
            _CACHE[did] = core.extract_info(deck)
        info = _CACHE[did]
        card_html = core.render_card(info, core.card_opts(flags))
        return {"ok": True, "token": token, "id": did, "info": info, "card_html": card_html}
    except urllib.error.HTTPError as e:
        return {"ok": False, "token": token, "id": did,
                "error": f"HTTP {e.code} (private or not found?)"}
    except Exception as e:  # noqa -- one bad deck must never kill the whole batch response
        return {"ok": False, "token": token, "id": did, "error": str(e)}


def _layout_payload(paper, gap_mm, card_scale):
    m = core.layout_metrics(paper, gap_mm, card_scale)
    page_size = "A4" if paper == "a4" else "letter"
    return {
        "m": m,
        "page_size": page_size,
        "css": core.card_css(m, page_size),
        "crop_html": core.cropmarks_html(m),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "DeckFacerGUI/1.0"

    def log_message(self, fmt, *args):
        pass  # keep the terminal quiet; errors are still surfaced to the page

    # -- helpers ---------------------------------------------------------- #
    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, data, content_type, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw or b"{}")

    # -- routing ------------------------------------------------------------ #
    # do_GET/do_POST are thin wrappers: an uncaught exception partway through a
    # handler (as happened when render_card() could throw inside _resolve())
    # kills the connection before any response is sent, which shows up in the
    # browser as an opaque "NetworkError" with no indication of what broke.
    # Catching here guarantees the client always gets a real HTTP response.
    def do_GET(self):
        try:
            self._do_GET()
        except Exception as e:  # noqa
            self._send_json({"error": f"server error: {e}"}, 500)

    def do_POST(self):
        try:
            self._do_POST()
        except Exception as e:  # noqa
            self._send_json({"error": f"server error: {e}"}, 500)

    def _do_GET(self):
        path = self.path.split("?", 1)[0]

        if path in STATIC_FILES:
            fname, ctype = STATIC_FILES[path]
            fp = GUI_DIR / fname
            if not fp.is_file():
                self._send_json({"error": f"missing GUI asset: {fname}"}, 404)
                return
            self._send_bytes(fp.read_bytes(), ctype)
            return

        if path.startswith("/output/"):
            name = path[len("/output/"):]
            if not OUTPUT_NAME_RE.match(name):
                self._send_json({"error": "invalid filename"}, 400)
                return
            fp = Path.cwd() / name
            if not fp.is_file():
                self._send_json({"error": "not found"}, 404)
                return
            self._send_bytes(fp.read_bytes(), "text/html; charset=utf-8")
            return

        self._send_json({"error": "not found"}, 404)

    def _do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            data = self._read_json()
        except (ValueError, json.JSONDecodeError):
            self._send_json({"error": "bad JSON body"}, 400)
            return

        if path == "/api/resolve":
            self._send_json(_resolve(data.get("token", ""), data.get("flags")))
            return

        if path == "/api/bulk":
            tokens = data.get("tokens") or []
            flags = data.get("flags")
            results = [_resolve(t, flags) for t in tokens]
            self._send_json({"results": results})
            return

        if path == "/api/rerender":
            ids = data.get("ids") or []
            opts = core.card_opts(data.get("flags"))
            cards, missing = {}, []
            for did in ids:
                if did not in _CACHE:
                    missing.append(did)
                    continue
                try:
                    cards[did] = core.render_card(_CACHE[did], opts)
                except Exception:  # noqa -- same guard as _resolve(): never kill the whole response
                    missing.append(did)
            self._send_json({"cards": cards, "missing": missing})
            return

        if path == "/api/user-decks":
            username = (data.get("username") or "").strip()
            if not username:
                self._send_json({"error": "username required"}, 400)
                return
            try:
                ids = core.enumerate_user_decks(username, commander_only=not data.get("all_formats"))
            except SystemExit as e:
                self._send_json({"error": str(e)}, 502)
                return
            self._send_json({"ids": ids})
            return

        if path == "/api/layout":
            paper = "a4" if data.get("paper") == "a4" else "letter"
            gap = float(data.get("gap", 3.0))
            scale = float(data.get("card_scale", 1.0))
            self._send_json(_layout_payload(paper, gap, scale))
            return

        if path == "/api/render":
            self._handle_render(data)
            return

        self._send_json({"error": "not found"}, 404)

    def _handle_render(self, data):
        flags = data.get("flags") or {}
        tokens = data.get("slots") or []
        paper = "a4" if flags.get("paper") == "a4" else "letter"
        commander_only = not flags.get("all_formats")

        cards, skipped = [], []
        for tok in tokens:
            if not tok:
                continue
            res = _resolve(tok)
            if not res["ok"]:
                skipped.append({"token": tok, "reason": res["error"]})
                continue
            info = res["info"]
            if commander_only and info["format_code"] != 3:
                skipped.append({"token": tok, "reason": f"not Commander ({info['format']})"})
                continue
            cards.append(info)

        if not cards:
            self._send_json({"ok": False, "error": "No usable decks in the sheet.", "skipped": skipped}, 400)
            return

        out_name = (flags.get("out") or "deck_cards.html").strip()
        if not out_name.endswith(".html"):
            out_name += ".html"
        if not OUTPUT_NAME_RE.match(out_name):
            out_name = "deck_cards.html"

        html = core.render_html(
            cards,
            paper=paper,
            opts=core.card_opts(flags),
            gap_mm=float(flags.get("gap", 3.0)),
            card_scale=float(flags.get("card_scale", 1.0)),
        )
        out_path = Path.cwd() / out_name
        out_path.write_text(html, encoding="utf-8")

        self._send_json({
            "ok": True,
            "path": str(out_path),
            "url": f"/output/{out_name}",
            "count": len(cards),
            "sheets": (len(cards) + 8) // 9,
            "skipped": skipped,
        })


def run(port=8765):
    if not GUI_DIR.is_dir():
        raise SystemExit(f"GUI assets not found at {GUI_DIR} -- reinstall/redownload the project.")
    if not core.HAVE_SEGNO:
        print("Note: `segno` isn't installed -- cards will show a printed link "
              "instead of a QR code. Run `pip install segno` for QR codes.\n")

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"DeckFacer GUI running at {url}  (Ctrl+C to stop)")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        server.server_close()


if __name__ == "__main__":
    run()

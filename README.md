# DeckFacer

Generates print-ready, Magic-card-sized "deck info" cards from your Archidekt
Commander decks. The output is a self-contained HTML file laid out as 3x3
grids of cards — print it to PDF and cut them out to label a shelf of
Commander decks.

Each card shows: commander(s) or the deck name as the big title (your choice),
EDH bracket badge (1-5 with name), WUBRG mana-symbol pips, color-identity name
(guild/shard/wedge/"Non-X"/Five-Color), format, card count, deck tags, an
optional short description, owner, a QR code linking to the deck, and a
left-edge color spine so a stack of decks is sortable by color. Every one of
those is independently toggleable, and the featured-art background's opacity
is adjustable (with an optional white text-halo for legibility over busy art).

## Requirements

- Python 3.7+ (nothing else — the entire tool is standard library).
- Optional: [`segno`](https://pypi.org/project/segno/) for QR codes on the
  cards. Without it, cards fall back to a printed `archidekt.com/decks/<id>`
  link. Install with:
  ```
  pip install segno
  ```

## Usage — command line

```
python3 archidekt_deck_cards.py --user <ArchidektName>      # all public Commander decks
python3 archidekt_deck_cards.py --file decks.txt            # list of deck URLs/IDs
python3 archidekt_deck_cards.py 11424116 <deck-url> ...     # ad-hoc IDs/URLs
```

This writes `deck_cards.html` (override with `--out`). Open it in a browser
→ Print → Save as PDF, with **Margins: None** and **Background graphics: on**.

Faint dashed guide lines run down the center of each gap between cards to
help keep interior cuts straight.

Key flags: `--all-formats`, `--a4`, `--gap <mm>` (default 3), `--card-scale
<float>` (e.g. 0.93), `--out <file>`. Card content/style: `--art-opacity
<0-1>` (default 0.45, or `--no-art` for 0), `--text-halo`,
`--feature-deck-name`, `--no-spine`, `--no-pips`, `--no-bracket`, `--no-tags`,
`--no-identity`, `--no-format`, `--no-count`, `--no-owner`, `--price`,
`--description`, `--no-qr`.

Decks must be Public (or pass exact IDs for Unlisted decks) — private decks
require a login and can't be fetched.

## Usage — GUI

A local browser GUI covers the same functionality as toggles, with a live
preview built from the same rendering code as the CLI (so the preview is
exactly what gets printed), click-to-assign deck slots, drag-to-reorder, and
bulk import by username or pasted list.

**Run it:**
```
python3 archidekt_deck_cards.py --gui
```

**Access it:** the command starts a local server and opens
`http://127.0.0.1:8765/` in your default browser automatically. If it
doesn't open (or you're on a headless machine forwarding the port), open
that URL yourself. Use `--port <N>` to run on a different port. Stop the
server with Ctrl+C in the terminal it's running in.

**Using it:**
- Click any empty slot to paste a deck URL/ID (or several, one per line).
- Hover a filled card for edit (✎) / remove (×) buttons; drag cards to
  reorder them.
- "Import" a username to bulk-add all their public decks, or paste a list
  of links/IDs and click "Add to sheet".
- All CLI flags (paper size, gap, card scale, art opacity, text halo, big
  title, every show/hide field, Commander-only filter, output filename) are
  toggles/sliders in the left panel and update the preview live.
- "Generate cards" writes the same kind of print-ready HTML file as the CLI
  and opens it in a new tab for printing.

A local server is required here (not a static page) because Archidekt's API
blocks cross-origin browser reads — the same reason the CLI has to run
locally rather than as a hosted web app. The GUI's backend (`gui_server.py`)
fetches decks server-side, exactly like the CLI does.

## Software Bill of Materials

Everything here is pure Python 3 standard library plus vanilla browser
JS/CSS — there is exactly one optional third-party dependency, and no
transitive/frontend dependencies at all (no npm, no build step, no CDN
assets).

| Component | Version | License | Purpose | Required? |
|---|---|---|---|---|
| [Python](https://www.python.org/) | 3.7+ | PSF License | Runtime | Yes |
| [segno](https://pypi.org/project/segno/) | any recent (tested with 1.6.x) | BSD 3-Clause | Generates the SVG QR code embedded on each card | No — falls back to a printed link |

Standard-library modules used (no separate install, ship with Python):
`argparse`, `html`, `json`, `re`, `sys`, `time`, `urllib`, `http.server`,
`webbrowser`, `pathlib`, `os`.

The frontend (`gui/index.html`, `gui/app.css`, `gui/app.js`) has zero
dependencies: no framework, no bundler, no package.json — plain HTML/CSS/JS
served as static files by `gui_server.py`.

Runtime network calls: only to `archidekt.com`'s public API (deck data) —
see [Archidekt](https://archidekt.com/) for their terms. The GUI serves
itself only on `127.0.0.1` and makes no other outbound calls.

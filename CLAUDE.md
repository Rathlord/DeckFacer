# Project: Archidekt Deck Info Cards

Generates print-ready, Magic-card-sized "deck info" cards from Archidekt Commander
decks. Output is a self-contained HTML file laid out as 3x3 grids of cards; the user
prints it to PDF and cuts them out to label ~100 Commander decks.

Main script: `archidekt_deck_cards.py` (pure Python 3 stdlib; optional `segno` for QR).
A local browser GUI (`gui_server.py` + `gui/`) covers the same functionality
with a live preview, also stdlib-only on the backend and vanilla JS/CSS on
the frontend — no new pip dependencies either way.

## Run it
CLI:
```
pip install segno                                  # optional, enables QR codes
python3 archidekt_deck_cards.py --user <ArchidektName>     # all public Commander decks
python3 archidekt_deck_cards.py --file decks.txt          # list of deck URLs/IDs
python3 archidekt_deck_cards.py 11424116 <deck-url> ...   # ad-hoc IDs/URLs
```
Then open the generated `deck_cards.html` in a browser → Print → Save as PDF,
with **Margins: None** and **Background graphics: on**.

Key flags: `--all-formats`, `--a4`, `--gap <mm>` (default 3), `--card-scale <float>`
(e.g. 0.93). Card content/style flags (one per `DEFAULT_CARD_OPTS` entry, see
Code map): `--art-opacity <0-1>` (default 0.45), `--no-art` (shorthand for
opacity 0), `--text-halo`, `--feature-deck-name`, `--no-spine`, `--no-pips`,
`--no-bracket`, `--no-tags`, `--no-identity`, `--no-format`, `--no-count`,
`--no-owner`, `--price`, `--description`, `--no-qr`.

GUI (all of the above as toggles, plus click-to-assign deck slots and a live
preview built from the same render functions as the CLI):
```
python3 archidekt_deck_cards.py --gui [--port 8765]
```
Opens `http://127.0.0.1:<port>/` in the default browser.

## What each card shows
Commander(s) or deck name as the big title (toggle which via `feature`), EDH
bracket badge (1-5 w/ name), WUBRG mana-symbol pips (real vector mana symbols
extracted from a reference SVG the user supplied, embedded as data URIs — see
`PIP_ICON_SVG` in Code map), color-identity name
(guild/shard/wedge/"Non-X"/Five-Color), format, card count,
deck tags, an optional short description, owner, a QR code linking to the deck,
and a left-edge color spine so a stack of decks is sortable by color. Every one
of these is independently togglable (`show_spine`, `show_pips`, etc. in
`DEFAULT_CARD_OPTS`) in both the CLI and GUI. A featured-art background is
optional (opacity slider, 0 = off) with an optional text-halo (white glow
behind all card text) for legibility over busy art.

## Archidekt API notes (undocumented and NOT stable — see 2026-07-16 breakage below; be polite — light use, link back)
- Single deck JSON: `https://archidekt.com/api/decks/{id}/`
- Username -> numeric user id: `https://archidekt.com/api/users/?username=<name>` (also returns `deckCount`).
- Public deck list for a user: `https://archidekt.com/api/decks/v3/?ownerId=<numeric id>&pageSize=50&page=N`.
  **`?owner=<username>&ownerexact=true` (what this doc said until 2026-07-16) is
  now silently ignored** — it returns the site-wide "most recent decks" feed
  regardless of the owner param, rather than erroring or returning nothing.
  Discovered because a GUI username-import spawned hundreds of strangers'
  decks. `enumerate_user_decks()` now resolves the id first via `/api/users/`
  and cross-checks every returned deck's `owner.id` against it, aborting
  loudly instead of silently absorbing an unfiltered feed if this endpoint's
  behavior drifts again. `pageSize` also appears to be ignored server-side
  (observed page size ~60 regardless of the requested value) — harmless since
  pagination termination relies on the `next` field, not on page size.
- Canonical deck URL (for QR): `https://archidekt.com/decks/{id}`
- Relevant top-level fields: `name`, `deckFormat` (3 = Commander), `edhBracket`
  (1-5 or null), `deckTags`, `owner.username`, `featured` (art-crop URL),
  `categories` (each has `name`, `isPremier`, `includedInDeck`), `cards`.
- Commander = any card whose category is a **premier** category (`isPremier: true`).
- Color identity comes from each commander's `oracleCard.colorIdentity`, given as
  full names ("White","Blue",...). Map to WUBRG. Deck identity = union of commanders'.
- Bracket names: 1 Exhibition, 2 Core, 3 Upgraded, 4 Optimized, 5 cEDH.

## Important constraints / decisions
- **Why a local script, not a web app:** Archidekt's API restricts cross-origin
  browser reads to its own domain (CORS), so a page on another origin can't fetch
  decks. Running locally (or from the terminal) avoids this entirely.
- **9-up spacing limit:** nine true-size 2.5x3.5in cards occupy 7.5x10.5in. On US
  Letter that leaves ~1in of horizontal slack but only ~0.5in vertical, so the row
  gap maxes ~2.3mm at true size. `layout_metrics()` clamps the gap to fit and warns.
  For larger even gaps use `--a4` or `--card-scale 0.93`. Layout uses `@page
  margin:0` and centers the page-sized `.sheet` grid, so print margins must be None.
- Decks must be Public (or pass exact IDs for Unlisted). Private decks need a login.
- **Card readability over art has two independent layers, deliberately no color
  wash anymore:** an early version also blended a per-color-identity gradient
  ("wash") between the art and a white veil; it was removed (user disliked it,
  and stacked with the veil it made the art nearly invisible anyway -- verified
  by simulating the exact opacity compositing in Pillow against a real deck's
  art, see git history around 2026-07-16). Readability now comes from (a) the
  fixed `::after` white gradient veil in `card_css()` (30-80% top-to-bottom,
  tuned so it doesn't fully wash out a user-raised art opacity), and (b)
  the optional per-card `text_halo` option (white text-shadow glow), which the
  user controls directly instead of it being baked into a fixed wash.

## Code map
- `layout_metrics()` — paper/card/gap math with clamping.
- `cropmarks_html()` — faint dashed guide lines down the center of each interior
  card gap (2 vertical + 2 horizontal per sheet), computed from `layout_metrics()`
  geometry; gap columns/rows are empty page background all the way through, so a
  full-length centered line never crosses a card.
- `enumerate_user_decks()` — paginates the v3 list endpoint.
- `extract_info()` — pulls commander/colors/bracket/count/price/description from
  deck JSON. `extract_description()` — Archidekt stores the description as
  Quill Delta JSON (`{"ops":[{"insert":"text"},...]}`, a rich-text-editor
  format), not plain text; this concatenates the string `insert` fragments.
- `DEFAULT_CARD_OPTS` / `card_opts(overrides)` — the single source of truth for
  every card content/style toggle (art opacity, text halo, feature, and one
  `show_*` bool per field). CLI flags, GUI checkboxes, and `render_card()`'s
  conditionals all key off these same names -- `card_opts()` merges a partial
  dict over the defaults, dropping unknown/None keys, so the GUI can send one
  combined flags object that also happens to carry unrelated layout/file
  fields (`paper`, `gap`, `out`, ...) without needing to filter them itself.
- `render_card(info, opts)` — builds one card's markup. `card_css()` — the full
  stylesheet, parameterized by `layout_metrics()` output; factored out of
  `render_html()` specifically so the GUI can embed byte-identical CSS in its
  live preview. `sheets_html()` — chunks cards into 9-up `.sheet` blocks.
  `render_html()` — assembles the full print document from the above.
- `PIP_ICON_SVG` — the 6 WUBRG+C mana-symbol icons, embedded as URL-encoded
  SVG data URIs. `pip_css()` emits one `.pip-{color} { background-image:
  url(...) }` rule per color in `card_css()`'s stylesheet, so each icon's
  markup appears once in the document regardless of how many pips/cards
  reference it -- `pip_html()` just emits `<span class="pip pip-W">` etc.
  W/U/B/R/G are extracted from a reference mana-symbol SVG the user supplied
  (https://gist.github.com/pca2/f67415d88d4ac7ea5354efc0a3faf440, a
  slightlymagic.net community asset, real vector art matching the official
  glyphs) -- coordinates translated to a local 0-110 viewBox, path data
  otherwise untouched. An earlier version tried raster crops from a sprite
  sheet the user found first; that looked "clunky" with visible cropping
  seams, which this vector version doesn't have. Extracting from that gist
  is non-trivial if it ever needs redoing: colored circles are normally
  `<circle>` elements but Green's is authored as a `<path>` (an Illustrator
  export quirk), and top-level `<g>` blocks aren't spatially ordered, so
  matching by grid position (like the sprite sheet) doesn't work -- match by
  each color's known circle fill hex instead (see git history around
  2026-07-16 for the extraction script). C (colorless) isn't in that sheet
  (it predates the real colorless-mana symbol) -- it's a small hand-drawn
  ring matching Magic's actual glyph, at the same 110x110 scale as the rest.
- `qr_data_uri()` — segno SVG data-URI QR (falls back to text link if segno absent).

## GUI architecture (`gui_server.py`, `gui/`)
- **Why a local server, not a static page:** the same CORS restriction noted
  above applies to the GUI — a page can't fetch Archidekt decks client-side.
  `gui_server.py` is a stdlib `http.server.ThreadingHTTPServer` that fetches
  deck JSON server-side (reusing `fetch_json`/`extract_info` from the CLI
  module) and hands the browser JSON over same-origin requests.
- The live preview is not a JS reimplementation of the card design — the
  server renders real `render_card()`/`card_css()`/`cropmarks_html()` output
  and the frontend just injects it into the DOM. What you see in the browser
  is built from the exact code that produces the printed file.
- In-memory `_CACHE` (keyed by deck id) in `gui_server.py` means toggling any
  `DEFAULT_CARD_OPTS` field, or paper/gap/scale, re-renders from cached deck
  info instantly without re-hitting Archidekt.
- API surface: `/api/resolve` (one deck), `/api/bulk` (paced list, for
  paste-import or `--user`-style bulk add), `/api/user-decks` (id listing via
  `enumerate_user_decks`), `/api/layout` (CSS + crop-line geometry for a given
  paper/gap/scale), `/api/rerender` (cheap re-render of any card-content
  option from cache, no Archidekt refetch), `/api/render` (writes the final
  `deck_cards.html`-equivalent to disk, same as the CLI, served back at
  `/output/<name>`). All of these except `/api/layout` pass their `flags`
  payload straight to `core.card_opts()` -- the JSON keys the GUI sends
  (`art_opacity`, `show_bracket`, etc.) are exactly `DEFAULT_CARD_OPTS`'s
  keys, no server-side name translation.
- `gui/app.js` keeps deck slots as a dense ordered list (no positional holes);
  a virtual trailing "add deck" tile is appended only at render time. Reorder
  is native HTML5 drag-and-drop; no drag/UI library used.

## Possible next steps discussed
- QR could point to the playtest/sandbox view or a Moxfield mirror instead.
- Larger/centered QR for easier scanning.

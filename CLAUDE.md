# Project: Archidekt Deck Info Cards

Generates print-ready, Magic-card-sized "deck info" cards from Archidekt Commander
decks. Output is a self-contained HTML file laid out as 3x3 grids of cards; the user
prints it to PDF and cuts them out to label ~100 Commander decks.

Main script: `archidekt_deck_cards.py` (pure Python 3 stdlib; optional `segno` for QR).

## Run it
```
pip install segno                                  # optional, enables QR codes
python3 archidekt_deck_cards.py --user <ArchidektName>     # all public Commander decks
python3 archidekt_deck_cards.py --file decks.txt          # list of deck URLs/IDs
python3 archidekt_deck_cards.py 11424116 <deck-url> ...   # ad-hoc IDs/URLs
```
Then open the generated `deck_cards.html` in a browser → Print → Save as PDF,
with **Margins: None** and **Background graphics: on**.

Key flags: `--all-formats`, `--a4`, `--no-art`, `--price`, `--no-qr`,
`--gap <mm>` (default 3), `--card-scale <float>` (e.g. 0.93).

## What each card shows
Commander(s) (partners handled), EDH bracket badge (1-5 w/ name), WUBRG color pips,
color-identity name (guild/shard/wedge/"Non-X"/Five-Color), format, card count,
deck tags, owner, a QR code linking to the deck, and a left-edge color spine so a
stack of decks is sortable by color.

## Archidekt API notes (undocumented but stable; be polite — light use, link back)
- Single deck JSON: `https://archidekt.com/api/decks/{id}/`
- Public deck list for a user: `https://archidekt.com/api/decks/v3/?owner=<name>&ownerexact=true&pageSize=50&page=N`
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

## Code map
- `layout_metrics()` — paper/card/gap math with clamping.
- `cropmarks_html()` — faint dashed guide lines down the center of each interior
  card gap (2 vertical + 2 horizontal per sheet), computed from `layout_metrics()`
  geometry; gap columns/rows are empty page background all the way through, so a
  full-length centered line never crosses a card.
- `enumerate_user_decks()` — paginates the v3 list endpoint.
- `extract_info()` — pulls commander/colors/bracket/count/price from deck JSON.
- `render_card()` / `render_html()` — build the HTML/CSS (inline styles, print @page).
- `qr_data_uri()` — segno SVG data-URI QR (falls back to text link if segno absent).

## Possible next steps discussed
- QR could point to the playtest/sandbox view or a Moxfield mirror instead.
- Larger/centered QR for easier scanning.

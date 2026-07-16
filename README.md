# DeckFacer

Generates print-ready, Magic-card-sized "deck info" cards from your Archidekt
Commander decks. The output is a self-contained HTML file laid out as 3x3
grids of cards — print it to PDF and cut them out to label a shelf of
Commander decks.

Each card shows: commander(s) (partners handled), EDH bracket badge (1-5 with
name), WUBRG color pips, color-identity name (guild/shard/wedge/"Non-X"/
Five-Color), format, card count, deck tags, owner, a QR code linking to the
deck, and a left-edge color spine so a stack of decks is sortable by color.

## Usage

```
pip install segno                                          # optional, enables QR codes
python3 archidekt_deck_cards.py --user <ArchidektName>      # all public Commander decks
python3 archidekt_deck_cards.py --file decks.txt            # list of deck URLs/IDs
python3 archidekt_deck_cards.py 11424116 <deck-url> ...     # ad-hoc IDs/URLs
```

Then open the generated `deck_cards.html` in a browser → Print → Save as PDF,
with **Margins: None** and **Background graphics: on**.

Faint dashed guide lines run down the center of each gap between cards to
help keep interior cuts straight.

Key flags: `--all-formats`, `--a4`, `--no-art`, `--price`, `--no-qr`,
`--gap <mm>` (default 3), `--card-scale <float>` (e.g. 0.93).

Pure Python 3 standard library, with one optional extra: `segno`, for QR
codes.

Decks must be Public (or pass exact IDs for Unlisted decks) — private decks
require a login and can't be fetched.

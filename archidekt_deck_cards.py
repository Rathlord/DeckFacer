#!/usr/bin/env python3
"""
archidekt_deck_cards.py
=======================
Generate print-ready, Magic-card-sized "deck info" cards from your Archidekt decks.

Each card shows: commander(s), color identity, EDH bracket, format, deck name,
archetype/tags, card count, (optional) price, and an Archidekt link/ID.

It outputs a single self-contained HTML file laid out as 3x3 grids of exact
2.5in x 3.5in cards. Open it in any browser and use "Print -> Save as PDF"
(set margins to Default/None, enable "Background graphics"), then cut them out.

Pure Python 3 standard library -- with one OPTIONAL extra: install `segno`
(`pip install segno`) to put a scannable QR code linking to each deck on the
card. Without it, the card falls back to a printed archidekt.com link.

--------------------------------------------------------------------------------
USAGE
--------------------------------------------------------------------------------
1) By username (grabs all your PUBLIC decks; Commander-only by default):

       python3 archidekt_deck_cards.py --user YourArchidektName

2) From a text file of deck URLs or IDs (one per line; # comments allowed):

       python3 archidekt_deck_cards.py --file decks.txt

3) Straight from the command line (URLs and/or bare IDs):

       python3 archidekt_deck_cards.py 11424116 https://archidekt.com/decks/123456/my_deck

Common options:
   --out cards.html      Output file (default: deck_cards.html)
   --all-formats         Include non-Commander decks too (default: Commander only)
   --a4                  Lay out for A4 paper instead of US Letter
   --no-art              Don't use each deck's featured art as a faded background
   --price               Show an approximate TCGplayer deck price on each card

Notes:
 * Decks must be Public (or Unlisted, if you pass the exact ID). Private decks
   require a login and can't be fetched.
 * The script pauses briefly between requests to be nice to Archidekt's API.
"""

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    import segno  # optional: enables QR codes
    HAVE_SEGNO = True
except ImportError:
    HAVE_SEGNO = False

API_DECK = "https://archidekt.com/api/decks/{id}/"
DECK_URL = "https://archidekt.com/decks/{id}"
API_LIST = "https://archidekt.com/api/decks/v3/"
API_USERS = "https://archidekt.com/api/users/"
USER_AGENT = "deck-info-card-maker/1.0 (personal deck labeling script)"

# Archidekt gives color identity as full names.
COLOR_TO_WUBRG = {
    "White": "W", "Blue": "U", "Black": "B", "Red": "R", "Green": "G",
    "Colorless": "C",
}
WUBRG_ORDER = ["W", "U", "B", "R", "G"]

# Pip + accent colors (modern, print-friendly).
PIP_STYLE = {
    "W": ("#f4efbf", "#5c5433"),   # (background, text)
    "U": ("#2f7dc4", "#ffffff"),
    "B": ("#3a3a42", "#ffffff"),
    "R": ("#cf4a2c", "#ffffff"),
    "G": ("#2f8f52", "#ffffff"),
    "C": ("#9a938a", "#ffffff"),
}


# Official-style mana-symbol icons for the WUBRG+colorless pips. W/U/B/R/G
# are extracted (coordinates translated to a local 0-110 viewBox, otherwise
# byte-identical path data) from a reference mana-symbol SVG the user provided:
# https://gist.github.com/pca2/f67415d88d4ac7ea5354efc0a3faf440 -- real vector
# art, not hand-drawn lookalikes. C (colorless) isn't in that sheet -- it's a
# small hand-drawn ring matching Magic's actual colorless-mana glyph, styled to
# the same 110x110 scale as the rest.
#
# Each is stored as a URL-encoded SVG data URI and referenced once per color from
# card_css() (.pip-W { background-image: url(...) } etc, see pip_css()) -- the
# encoded markup appears once in the document regardless of how many pips/cards
# use it, not once per <span>.
PIP_ICON_SVG = {
    "W": "data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20viewBox%3D%220%200%20110%20110%22%3E%3Cg%20transform%3D%22translate%28530.0%2C5.0%29%22%3E%3Cg%3E%20%3Ccircle%20fill%3D%22%23F8F6D8%22%20cx%3D%22-475%22%20cy%3D%2250%22%20r%3D%2250%22/%3E%20%3C/g%3E%20%3Cpath%20fill%3D%22%230D0F0F%22%20d%3D%22M-427.309%2C57.064c-6.561-3.699-10.768-5.551-12.617-5.551c-1.344%2C0-2.395%2C1.032-3.154%2C3.092%20c-0.758%2C2.063-2.27%2C3.09-4.541%2C3.09c-0.926%2C0-2.818-0.336-5.678-1.008c-1.598%2C2.44-2.398%2C3.996-2.398%2C4.668%20c0%2C0.926%2C0.689%2C2.016%2C2.064%2C3.281c1.375%2C1.262%2C2.535%2C1.891%2C3.482%2C1.891c0.602%2C0%2C1.416-0.125%2C2.449-0.379%20c1.031-0.25%2C1.721-0.377%2C2.064-0.377c1.033%2C0%2C1.547%2C1.893%2C1.547%2C5.678c0%2C3.617-0.84%2C9.168-2.523%2C16.654%20c-2.188-8.58-4.5-12.871-6.938-12.871c-0.338%2C0-1.031%2C0.252-2.082%2C0.76c-1.053%2C0.502-1.83%2C0.754-2.334%2C0.754%20c-2.438%2C0-4.625-2.227-6.561-6.688c-3.869%2C0.59-5.805%2C2.567-5.805%2C5.934c0%2C1.684%2C0.777%2C3.027%2C2.336%2C4.035%20c1.553%2C1.008%2C2.334%2C1.727%2C2.334%2C2.145c0%2C2.273-3.324%2C5.764-9.969%2C10.473c-3.531%2C2.523-5.973%2C4.289-7.316%2C5.297%20c1.174-1.512%2C2.352-3.487%2C3.533-5.928c1.344-2.775%2C2.018-4.92%2C2.018-6.436c0-0.84-0.967-2.02-2.902-3.533%20c-1.936-1.512-2.9-3.111-2.9-4.793c0-1.428%2C0.502-3.193%2C1.512-5.299c-1.094-1.262-2.395-1.895-3.91-1.895%20c-3.365%2C0-5.045%2C1.096-5.045%2C3.28c0-1.514%2C0-0.379%2C0%2C3.406c0.082%2C2.776-2.02%2C4.164-6.311%2C4.164c-3.279%2C0-8.791-0.759-16.527-2.271%20c8.748-2.188%2C13.121-4.711%2C13.121-7.57c0%2C0.336-0.168-0.672-0.504-3.028c-0.338-2.604%2C1.514-4.961%2C5.551-7.063%20c-0.758-3.867-2.773-5.806-6.057-5.806c-0.504%2C0-1.432%2C0.884-2.775%2C2.647c-1.346%2C1.771-2.607%2C2.652-3.783%2C2.652%20c-2.02%2C0-4.629-2.186-7.822-6.563c-1.516-2.184-3.83-5.424-6.941-9.715c1.934%2C1.012%2C3.869%2C2.02%2C5.805%2C3.031%20c2.523%2C1.176%2C4.541%2C1.766%2C6.057%2C1.766c1.178%2C0%2C2.334-1.031%2C3.469-3.092c1.135-2.061%2C2.629-3.092%2C4.479-3.092%20c0.254%2C0%2C1.936%2C0.504%2C5.047%2C1.516c1.596-2.439%2C2.398-4.248%2C2.398-5.426c0-1.01-0.611-2.166-1.83-3.471%20c-1.221-1.303-2.334-1.955-3.344-1.955c-0.422%2C0-1.072%2C0.125-1.957%2C0.379c-0.881%2C0.252-1.533%2C0.379-1.953%2C0.379%20c-1.516%2C0-2.273-1.893-2.273-5.678c0-1.01%2C0.969-6.77%2C2.904-17.285c-0.086%2C1.26%2C0.461%2C3.617%2C1.639%2C7.064%20c1.43%2C4.207%2C3.111%2C6.309%2C5.049%2C6.309c0.334%2C0%2C1.008-0.252%2C2.018-0.758c1.008-0.504%2C1.807-0.754%2C2.396-0.754%20c1.934%2C0%2C3.531%2C1.094%2C4.795%2C3.277l1.893%2C3.406c1.766%2C0%2C3.238-0.629%2C4.414-1.891c1.178-1.262%2C1.768-2.777%2C1.768-4.543%20c0-1.85-0.777-3.26-2.334-4.227c-1.559-0.967-2.336-1.703-2.336-2.207c0-1.768%2C2.777-4.752%2C8.328-8.958%20c4.457-3.363%2C7.359-5.34%2C8.707-5.93c-3.617%2C4.879-5.426%2C8.451-5.426%2C10.724c0%2C1.178%2C0.713%2C2.441%2C2.145%2C3.785%20c1.766%2C1.598%2C2.775%2C2.734%2C3.027%2C3.406c0.84%2C1.938%2C0.756%2C4.586-0.252%2C7.949c2.271%2C1.6%2C3.994%2C2.396%2C5.174%2C2.396%20c2.436%2C0%2C3.658-1.264%2C3.658-3.785c0-0.252-0.105-1.051-0.314-2.396c-0.213-1.344-0.273-2.102-0.191-2.271%20c0.336-1.178%2C2.65-1.768%2C6.939-1.768c2.691%2C0%2C8.283%2C0.758%2C16.781%2C2.273c-1.852%2C0.504-4.627%2C1.26-8.326%2C2.27%20c-3.365%2C1.01-5.049%2C2.145-5.049%2C3.406c0%2C0.59%2C0.209%2C1.598%2C0.631%2C3.027c0.42%2C1.432%2C0.633%2C2.48%2C0.633%2C3.156%20c0%2C1.176-0.758%2C2.27-2.271%2C3.277l-4.291%2C3.031c1.01%2C1.852%2C1.682%2C2.945%2C2.02%2C3.279c0.84%2C1.008%2C1.975%2C1.514%2C3.406%2C1.514%20c1.01%2C0%2C1.934-0.883%2C2.775-2.648c0.84-1.768%2C2.188-2.65%2C4.037-2.65c2.27%2C0%2C4.838%2C2.104%2C7.697%2C6.311%20C-433.156%2C48.697-430.674%2C52.27-427.309%2C57.064z%20M-455.316%2C49.748c0-5.381-1.979-10.051-5.932-14.006%20c-3.953-3.953-8.621-5.93-14.004-5.93c-5.469%2C0-10.18%2C1.957-14.131%2C5.869c-3.953%2C3.91-5.973%2C8.6-6.055%2C14.066%20c-0.086%2C5.383%2C1.912%2C10.03%2C5.992%2C13.938c4.08%2C3.912%2C8.811%2C5.869%2C14.193%2C5.869c5.719%2C0%2C10.492-1.873%2C14.318-5.615%20C-457.105%2C60.199-455.234%2C55.469-455.316%2C49.748z%20M-457.209%2C49.748c0%2C5.131-1.725%2C9.381-5.174%2C12.74%20c-3.451%2C3.367-7.74%2C5.049-12.869%2C5.049c-4.963%2C0-9.211-1.723-12.742-5.174c-3.531-3.445-5.299-7.652-5.299-12.615%20c0-4.877%2C1.785-9.064%2C5.359-12.553c3.578-3.49%2C7.803-5.238%2C12.682-5.238c4.877%2C0%2C9.104%2C1.766%2C12.68%2C5.301%20C-458.998%2C40.791-457.209%2C44.953-457.209%2C49.748z%22/%3E%3C/g%3E%3C/svg%3E",
    "U": "data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20viewBox%3D%220%200%20110%20110%22%3E%3Cg%20transform%3D%22translate%28425.0%2C5.0%29%22%3E%3Cg%3E%20%3Ccircle%20fill%3D%22%23C1D7E9%22%20cx%3D%22-370%22%20cy%3D%2250%22%20r%3D%2250%22/%3E%20%3C/g%3E%20%3Cpath%20fill%3D%22%230D0F0F%22%20d%3D%22M-352.512%2C83.719c-4.787%2C4.871-10.684%2C7.307-17.688%2C7.307c-7.861%2C0-14.098-2.69-18.711-8.073%20c-4.359-5.127-6.537-11.662-6.537-19.606c0-8.543%2C3.717-18.286%2C11.15-29.224c6.064-8.969%2C13.199-16.83%2C21.402-23.58%20c-1.197%2C5.469-1.793%2C9.355-1.793%2C11.662c0%2C5.299%2C1.664%2C10.467%2C4.996%2C15.508c4.102%2C5.98%2C7.219%2C10.426%2C9.357%2C13.328%20c3.332%2C5.043%2C4.998%2C9.955%2C4.998%2C14.737C-345.336%2C72.871-347.729%2C78.852-352.512%2C83.719z%20M-352.641%2C56.357%20c-1.281-2.861-2.777-4.762-4.486-5.703c0.256%2C0.514%2C0.385%2C1.24%2C0.385%2C2.18c0%2C1.795-0.512%2C4.357-1.539%2C7.689l-1.664%2C5.127%20c0%2C2.99%2C1.492%2C4.486%2C4.484%2C4.486c3.16%2C0%2C4.742-2.095%2C4.742-6.281C-350.719%2C61.721-351.359%2C59.223-352.641%2C56.357z%22/%3E%3C/g%3E%3C/svg%3E",
    "B": "data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20viewBox%3D%220%200%20110%20110%22%3E%3Cg%20transform%3D%22translate%28320.0%2C5.0020000000000024%29%22%3E%3Cg%3E%20%3Ccircle%20fill%3D%22%23BAB1AB%22%20cx%3D%22-265%22%20cy%3D%2249.998%22%20r%3D%2250%22/%3E%20%3C/g%3E%20%3Cpath%20fill%3D%22%230D0F0F%22%20d%3D%22M-224.305%2C48.619c0%2C5.518-2.008%2C9.281-6.02%2C11.287c-1.172%2C0.586-4.85%2C1.379-11.037%2C2.383%20c-4.012%2C0.67-6.018%2C2.217-6.018%2C4.639v10.158c0%2C0.422%2C0.125%2C1.715%2C0.375%2C3.889l0.377%2C4.014c0%2C1.255-0.293%2C3.306-0.879%2C6.146%20c-1.588%2C0.334-3.428%2C0.709-5.518%2C1.132c-0.67-2.511-1.004-4.224-1.004-5.146c0-0.416%2C0.105-1.045%2C0.313-1.882%20c0.207-0.834%2C0.316-1.461%2C0.316-1.883c0-0.58-0.52-2.213-1.559-4.887h-1.945c-0.258%2C0.418-0.344%2C0.961-0.26%2C1.629%20c0.334%2C1.422%2C0.459%2C2.633%2C0.377%2C3.637c-1.422%2C1.004-3.387%2C2.341-5.895%2C4.013c-0.586-0.166-0.793-0.25-0.629-0.25v-8.904%20c-0.164-0.416-0.584-0.581-1.254-0.502h-1.504l-1.504%2C11.787c-1.174%2C0.084-2.592%2C0.084-4.264%2C0%20c-0.588-2.758-1.631-6.853-3.135-12.289h-1.004c-0.922%2C2.929-1.422%2C4.519-1.506%2C4.769c0%2C0.334%2C0.104%2C0.981%2C0.314%2C1.942%20c0.207%2C0.962%2C0.313%2C1.609%2C0.313%2C1.943c0%2C0.25-0.084%2C0.877-0.25%2C1.881l-0.377%2C3.01c-0.168%2C0.166-0.377%2C0.25-0.627%2C0.25%20c-2.508%2C0-4.182-0.627-5.016-1.879c-0.836-1.256-1.172-3.012-1.004-5.271l1.004-15.047c0-0.252%2C0.082-0.586%2C0.25-1.004%20c0.164-0.418%2C0.25-0.711%2C0.25-0.877c0-0.67-0.711-2.008-2.131-4.014c-0.248-0.082-1.549-0.377-3.887-0.879%20c-1.424-0.334-4.225-0.918-8.402-1.756c-5.771-1.084-8.654-5.725-8.654-13.92c0-12.207%2C5.018-22.365%2C15.051-30.475%20c0.414%2C2.258%2C1.127%2C5.266%2C2.129%2C9.029c0.754%2C0.17%2C2.385%2C0.545%2C4.891%2C1.129c0.504%2C0.168%2C3.053%2C1.088%2C7.652%2C2.76%20c-2.344-1.422-5.393-3.719-9.156-6.898c-1.422-1.672-2.133-4.471-2.133-8.4c0-0.92%2C1.59-2.008%2C4.768-3.264%20c2.84-1.17%2C4.975-1.836%2C6.396-2.006c4.514-0.582%2C7.984-0.879%2C10.41-0.879c10.449%2C0%2C18.891%2C2.678%2C25.328%2C8.029%20c-2.088%2C2.426-5.684%2C5.014-10.783%2C7.773c2.008%2C0.084%2C4.934-0.707%2C8.779-2.383c3.844-1.67%2C5.475-2.508%2C4.891-2.508%20c0.668%2C0%2C2.008%2C1.34%2C4.014%2C4.014c1.504%2C2.006%2C2.715%2C3.807%2C3.637%2C5.391c2.674%2C4.768%2C4.471%2C9.908%2C5.393%2C15.426%20c0%2C1.926%2C0.041%2C3.305%2C0.125%2C4.139v1.004H-224.305z%20M-272.336%2C50.877c0-3.594-1.568-7.002-4.703-10.223%20c-3.137-3.219-6.502-4.826-10.096-4.826c-3.178%2C0-5.977%2C1.348-8.402%2C4.039c-2.426%2C2.693-3.637%2C5.682-3.637%2C8.963%20c0%2C2.859%2C1.379%2C4.713%2C4.139%2C5.553c1.756%2C0.506%2C4.219%2C0.801%2C7.398%2C0.883h6.898C-275.141%2C55.35-272.336%2C53.887-272.336%2C50.877z%20M-258.668%2C66.43v-3.889c-0.584-1.086-1.17-2.215-1.754-3.387c-0.502-1.674-1.422-4.014-2.76-7.025l-1.381%2C14.674%20c0%2C1.172-0.25%2C1.756-0.752%2C1.756c-0.334%2C0-0.584-0.082-0.752-0.248c-0.586-8.863-0.879-12.709-0.879-11.541v-4.387%20c-0.168-0.254-0.375-0.379-0.625-0.379c-2.844%2C2.93-4.264%2C7.652-4.264%2C14.172c0%2C3.596%2C0.33%2C5.811%2C1.002%2C6.648%20c0.67-0.166%2C1.422-0.459%2C2.258-0.877c0.334-0.168%2C1.295-0.252%2C2.887-0.252c1.584%2C0%2C3.51%2C0.502%2C5.766%2C1.504%20C-259.086%2C73.199-258.668%2C70.943-258.668%2C66.43z%20M-230.324%2C48.955c0-3.367-1.254-6.375-3.762-9.025%20c-2.51-2.648-5.395-3.975-8.652-3.975c-3.512%2C0-6.795%2C1.607-9.846%2C4.826c-3.053%2C3.219-4.578%2C6.584-4.578%2C10.096%20c0%2C2.928%2C1.42%2C4.389%2C4.264%2C4.389h14.422C-233.043%2C55.184-230.324%2C53.08-230.324%2C48.955z%22/%3E%3C/g%3E%3C/svg%3E",
    "R": "data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20viewBox%3D%220%200%20110%20110%22%3E%3Cg%20transform%3D%22translate%28215.0%2C5.0%29%22%3E%3Cg%3E%20%3Ccircle%20fill%3D%22%23E49977%22%20cx%3D%22-160%22%20cy%3D%2250%22%20r%3D%2250%22/%3E%20%3C/g%3E%20%3Cpath%20fill%3D%22%230D0F0F%22%20d%3D%22M-118.035%2C66.617c-3.736%2C8.912-11.16%2C13.367-22.275%2C13.367c-2.037%2C0-4.246%2C0.254-6.621%2C0.762%20c-3.564%2C0.764-5.346%2C1.828-5.346%2C3.186c0%2C0.424%2C0.295%2C0.91%2C0.891%2C1.463c0.592%2C0.553%2C1.104%2C0.826%2C1.527%2C0.826%20c-2.123%2C0-0.68%2C0.064%2C4.326%2C0.191c5.008%2C0.127%2C8.148%2C0.191%2C9.422%2C0.191c-7.383%2C4.326-19.732%2C6.319-37.043%2C5.981%20c-5.688-0.084-10.566-2.588-14.639-7.51c-3.992-4.669-5.984-9.888-5.984-15.658c0-6.108%2C2.057-11.308%2C6.176-15.595%20c4.113-4.282%2C9.229-6.427%2C15.338-6.427c1.357%2C0%2C3.16%2C0.297%2C5.41%2C0.891c2.248%2C0.594%2C3.756%2C0.891%2C4.518%2C0.891%20c3.139%2C0%2C7.045-1.293%2C11.713-3.883c4.666-2.588%2C6.875-3.883%2C6.621-3.883c-0.85%2C8.912-3.82%2C14.896-8.914%2C17.948%20c-3.648%2C2.123-5.473%2C4.201-5.473%2C6.236c0%2C1.273%2C0.764%2C2.293%2C2.291%2C3.057c1.188%2C0.595%2C2.502%2C0.892%2C3.945%2C0.892%20c2.207%2C0%2C4.371-1.356%2C6.494-4.071c2.119-2.718%2C3.055-5.177%2C2.801-7.386c-0.254-2.545-0.084-5.603%2C0.51-9.164%20c0.168-1.02%2C0.783-2.27%2C1.844-3.754c1.061-1.486%2C2.016-2.398%2C2.865-2.738c0%2C0.762-0.275%2C2.037-0.828%2C3.818%20c-0.553%2C1.781-0.826%2C3.1-0.826%2C3.947c0%2C1.867%2C0.508%2C3.309%2C1.527%2C4.326c1.525-0.592%2C2.883-2.502%2C4.074-5.729%20c1.016-2.459%2C1.609-4.836%2C1.781-7.127c-3.566-0.17-6.982-1.781-10.248-4.838c-3.268-3.057-4.9-6.365-4.9-9.928%20c0-0.594%2C0.082-1.188%2C0.256-1.783c0.508%2C0.764%2C1.271%2C1.953%2C2.289%2C3.564c1.443%2C2.121%2C2.547%2C3.182%2C3.313%2C3.182%20c1.016%2C0%2C1.525-1.061%2C1.525-3.182c0-2.715-0.723-5.176-2.164-7.383c-1.613-2.631-3.693-3.947-6.238-3.947%20c-1.189%2C0-2.971%2C0.637-5.344%2C1.91c-2.379%2C1.271-4.543%2C1.91-6.492%2C1.91c-0.596%2C0-3.229-0.766-7.895-2.293%20c8.23-1.355%2C12.348-2.586%2C12.348-3.691c0-2.885-5.645-4.838-16.93-5.855c-1.105-0.084-3.141-0.254-6.111-0.51%20c0.338-0.424%2C2.758-0.891%2C7.258-1.4c3.818-0.422%2C6.492-0.637%2C8.018-0.637c20.197%2C0%2C33.012%2C9.805%2C38.443%2C29.408%20c0.934-0.773%2C1.402-2.066%2C1.402-3.871c0-2.324-0.68-5.25-2.037-8.777c-0.512-1.375-1.318-3.441-2.42-6.193%20c6.957%2C8.867%2C10.439%2C17.27%2C10.439%2C25.199c0%2C4.178-0.979%2C7.973-2.93%2C11.381c-1.27%2C2.303-3.65%2C5.244-7.127%2C8.826%20c-3.48%2C3.58-5.857%2C6.352-7.131%2C8.313c4.668-1.271%2C7.725-2.248%2C9.168-2.928c3.223-1.44%2C6.15-3.606%2C8.783-6.492%20C-116.635%2C62.756-117.102%2C64.412-118.035%2C66.617z%20M-173.537%2C16.592c0%2C1.525-0.85%2C2.502-2.545%2C2.926l-3.311%2C0.51%20c-1.189%2C0.594-2.928%2C2.928-5.219%2C7c-0.256-1.271-0.637-3.053-1.146-5.346c-0.764%2C0.086-2.035%2C0.764-3.818%2C2.037%20c-0.764%2C0.594-1.996%2C1.484-3.693%2C2.672c0.512-3.055%2C2.207-6.148%2C5.094-9.293c3.055-3.477%2C6.025-5.217%2C8.91-5.217%20C-175.447%2C11.881-173.537%2C13.453-173.537%2C16.592z%20M-151.387%2C28.301c0%2C1.443-0.785%2C2.654-2.355%2C3.629%20c-1.57%2C0.977-3.119%2C1.465-4.646%2C1.465c-2.037%2C0-3.863-1.146-5.473-3.438c-1.955-2.801-3.947-4.625-5.984-5.477%20c0.424-0.422%2C0.934-0.635%2C1.529-0.635c0.764%2C0%2C2.055%2C0.594%2C3.881%2C1.781c1.824%2C1.189%2C2.99%2C1.783%2C3.502%2C1.783%20c0.424%2C0%2C1.123-0.594%2C2.1-1.783c0.975-1.188%2C2.057-1.781%2C3.246-1.781C-152.787%2C23.846-151.387%2C25.332-151.387%2C28.301z%22/%3E%3C/g%3E%3C/svg%3E",
    "G": "data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20viewBox%3D%220%200%20110%20110%22%3E%3Cg%20transform%3D%22translate%28110.0%2C5.0%29%22%3E%3Cg%3E%20%3Cpath%20fill%3D%22%23A3C095%22%20d%3D%22M-5%2C49.998C-5%2C77.613-27.385%2C100-55.002%2C100C-82.615%2C100-105%2C77.613-105%2C49.998%20C-105%2C22.385-82.615%2C0-55.002%2C0C-27.385%2C0-5%2C22.385-5%2C49.998z%22/%3E%20%3C/g%3E%20%3Cpath%20fill%3D%22%230D0F0F%22%20d%3D%22M-11.238%2C56.225c0%2C1.668-0.645%2C3.164-1.936%2C4.498c-1.289%2C1.332-2.77%2C1.998-4.436%2C1.998%20c-2.662%2C0-4.623-1.25-5.869-3.748l-5.871-0.25c-1.252%2C0-3.709%2C0.543-7.371%2C1.625c-3.914%2C1.082-6.164%2C1.957-6.746%2C2.623%20c-0.916%2C0.998-1.664%2C3.332-2.248%2C6.996c-0.502%2C2.998-0.748%2C5.205-0.748%2C6.621c0%2C2.246%2C0.352%2C3.893%2C1.061%2C4.934%20s2.166%2C1.916%2C4.371%2C2.623c2.205%2C0.707%2C3.561%2C1.104%2C4.061%2C1.187c0.332%2C0%2C0.873-0.041%2C1.625-0.125h1.498c1.08%2C0%2C2.205%2C0.17%2C3.373%2C0.5%20c1.666%2C0.5%2C2.375%2C1.166%2C2.125%2C2c-1.168-0.166-3.207%2C0.084-6.121%2C0.75l3.496%2C1.748c0%2C1-1.416%2C1.498-4.246%2C1.498%20c-0.752%2C0-1.771-0.166-3.063-0.498c-1.291-0.336-2.145-0.5-2.559-0.5h-1.625c-0.082%2C0.832-0.334%2C2.08-0.75%2C3.746%20c-1.418-0.084-3.08-0.918-4.996-2.498c-1.918-1.58-3.123-2.373-3.621-2.373c-0.502%2C0-1.211%2C0.793-2.125%2C2.373%20c-0.918%2C1.58-1.375%2C2.664-1.375%2C3.248c-1.082-0.584-1.996-1.668-2.75-3.248c-0.332-1.084-0.707-2.166-1.121-3.248%20c-0.832%2C0.084-2.375%2C1.834-4.621%2C5.248h-0.627c-0.166-0.252-0.795-2-1.873-5.248c-2.582-0.832-4.996-1.248-7.246-1.248%20c-1.082%2C0-2.748%2C0.25-4.996%2C0.748l-3.496-0.248c0.498-0.5%2C1.955-1.457%2C4.371-2.873c2.83-1.666%2C4.996-2.5%2C6.496-2.5%20c0.246%2C0%2C0.578%2C0.043%2C1%2C0.125c0.414%2C0.086%2C0.75%2C0.125%2C1%2C0.125c0.578%2C0%2C1.518-0.312%2C2.809-0.938c1.291-0.623%2C2.039-1.186%2C2.246-1.684%20c0.211-0.504%2C0.316-1.793%2C0.316-3.875c0-4.746-1.25-8.285-3.75-10.617c-2.168-2.082-5.746-3.58-10.744-4.498%20c-1.332%2C4.746-5.08%2C7.123-11.24%2C7.123c-2%2C0-3.998-1.207-5.996-3.623c-1.996-2.416-2.996-4.623-2.996-6.621%20c0-3.082%2C1.287-5.621%2C3.869-7.623c-2.08-2.162-3.121-4.369-3.121-6.617c0-2.084%2C0.643-3.914%2C1.936-5.5%20c1.291-1.578%2C2.977-2.496%2C5.059-2.748c-0.166-2.662%2C0.707-4.496%2C2.623-5.496c-0.916-0.914-1.373-2.537-1.373-4.869%20c0-2.748%2C0.916-5.039%2C2.748-6.871c1.83-1.832%2C4.121-2.75%2C6.869-2.75c3%2C0%2C5.457%2C1.045%2C7.371%2C3.125%20c2.416-8.244%2C7.621-12.367%2C15.613-12.367c4.164%2C0%2C7.828%2C1.666%2C10.994%2C4.998c1.166%2C1.248%2C1.748%2C1.916%2C1.748%2C1.996%20c-1%2C0-0.498-0.188%2C1.5-0.561c1.996-0.375%2C3.453-0.563%2C4.373-0.563c3.246%2C0%2C6.119%2C1.207%2C8.619%2C3.623%20c2.164%2C2.166%2C3.664%2C4.912%2C4.498%2C8.244c0.58%2C0.084%2C1.498%2C0.332%2C2.748%2C0.748c1.83%2C0.92%2C2.748%2C2.498%2C2.748%2C4.748%20c0%2C0.418-0.336%2C1.209-1%2C2.373c5.328%2C2.998%2C7.994%2C7.162%2C7.994%2C12.492c0%2C1.498-0.582%2C3.584-1.748%2C6.247%20C-12.318%2C51.977-11.238%2C53.811-11.238%2C56.225z%20M-62.705%2C61.721v-1.623c0-1.914-0.936-3.664-2.809-5.246%20c-1.875-1.582-3.77-2.373-5.684-2.373c-2.334%2C0-4.496%2C0.541-6.496%2C1.621C-73.281%2C53.852-68.283%2C56.393-62.705%2C61.721z%20M-64.951%2C46.232c-1.25-1.418-2.332-2.875-3.25-4.373c-3.498%2C0.916-5.246%2C1.957-5.246%2C3.121c1-0.08%2C2.457%2C0.105%2C4.371%2C0.564%20C-67.162%2C46.003-65.785%2C46.232-64.951%2C46.232z%20M-57.33%2C42.359v-5.496c-2-0.332-3.211-0.5-3.623-0.5v1.873L-57.33%2C42.359z%20M-41.092%2C38.861c-1-0.416-2.875-1.25-5.621-2.498v10.742C-42.801%2C44.855-40.928%2C42.107-41.092%2C38.861z%20M-34.225%2C53.602%20l-2.746-3.373c-1.664%2C1.167-3.352%2C2.354-5.061%2C3.561c-1.709%2C1.207-3.186%2C2.563-4.432%2C4.06%20C-42.717%2C55.848-38.635%2C54.436-34.225%2C53.602z%22/%3E%3C/g%3E%3C/svg%3E",
    "C": "data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20viewBox%3D%220%200%20110%20110%22%3E%3Ccircle%20cx%3D%2255%22%20cy%3D%2255%22%20r%3D%2250%22%20fill%3D%22%239a938a%22/%3E%3Ccircle%20cx%3D%2255%22%20cy%3D%2255%22%20r%3D%2222%22%20fill%3D%22none%22%20stroke%3D%22%233a362f%22%20stroke-width%3D%227%22/%3E%3C/svg%3E",
}

BRACKET_NAMES = {1: "Exhibition", 2: "Core", 3: "Upgraded", 4: "Optimized", 5: "cEDH"}

FORMAT_NAMES = {
    1: "Standard", 2: "Modern", 3: "Commander", 4: "Legacy", 5: "Vintage",
    6: "Pauper", 7: "Custom", 8: "Old School", 9: "Future Std", 10: "Penny",
    11: "1v1 Cmdr", 12: "Duel Cmdr", 13: "Brawl", 14: "Oathbreaker",
    15: "Pioneer", 16: "Historic", 17: "Pauper Cmdr", 18: "Alchemy",
    19: "Explorer", 20: "Historic Brawl", 21: "Gladiator", 22: "Premodern",
    23: "PreDH", 24: "Timeless", 25: "Canadian Highlander",
}

# Color-identity display names keyed by a sorted WUBRG string.
IDENTITY_NAMES = {
    "": "Colorless", "W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green",
    "WU": "Azorius", "UB": "Dimir", "BR": "Rakdos", "RG": "Gruul", "WG": "Selesnya",
    "WB": "Orzhov", "UR": "Izzet", "BG": "Golgari", "WR": "Boros", "UG": "Simic",
    "WUB": "Esper", "UBR": "Grixis", "BRG": "Jund", "WRG": "Naya", "WUG": "Bant",
    "WBR": "Mardu", "URG": "Temur", "WBG": "Abzan", "WUR": "Jeskai", "UBG": "Sultai",
    "WUBR": "Non-Green", "WUBG": "Non-Red", "WURG": "Non-Black",
    "WBRG": "Non-Blue", "UBRG": "Non-White",
    "WUBRG": "Five-Color",
}


# --------------------------------------------------------------------------- #
# Fetching
# --------------------------------------------------------------------------- #
def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_deck_id(token):
    """Accept a bare ID or any Archidekt deck URL and return the numeric ID."""
    token = token.strip()
    if not token:
        return None
    m = re.search(r"/decks/(\d+)", token)
    if m:
        return m.group(1)
    if token.isdigit():
        return token
    m = re.search(r"(\d{3,})", token)  # last-ditch: first long number
    return m.group(1) if m else None


def resolve_user_id(username):
    """Username -> numeric Archidekt user id (the deck-list endpoint needs the id).

    NOTE: `?owner=<username>&ownerexact=true` on the v3 list endpoint used to
    work but as of this writing is silently ignored -- it returns the
    site-wide "most recent decks" feed regardless of the owner param,
    instead of erroring or returning nothing. `?ownerId=<numeric id>` is the
    one that actually filters. Since that's undocumented behavior that has
    already drifted once, enumerate_user_decks() also double-checks each
    result's owner rather than trusting the filter blindly.
    """
    params = urllib.parse.urlencode({"username": username})
    try:
        data = fetch_json(f"{API_USERS}?{params}")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Could not look up Archidekt user '{username}' (HTTP {e.code}).")
    results = data.get("results") or []
    if not results:
        raise SystemExit(f"No Archidekt user named '{username}' found.")
    return results[0]["id"]


def enumerate_user_decks(username, commander_only):
    """Return a list of deck IDs for a user's PUBLIC decks via the list API."""
    user_id = resolve_user_id(username)
    ids, page = [], 1
    while True:
        params = urllib.parse.urlencode({"ownerId": user_id, "pageSize": 50, "page": page})
        url = f"{API_LIST}?{params}"
        try:
            data = fetch_json(url)
        except urllib.error.HTTPError as e:
            raise SystemExit(
                f"Could not list decks for '{username}' (HTTP {e.code}).\n"
                f"The list endpoint may have changed. Fall back to --file with a "
                f"list of deck URLs, which is the most reliable method."
            )
        results = data.get("results", data if isinstance(data, list) else [])
        if not results:
            break
        for d in results:
            owner = d.get("owner") or {}
            if owner.get("id") != user_id:
                # The owner filter has silently no-op'd before (see docstring
                # above) -- bail rather than pulling in the entire site feed.
                raise SystemExit(
                    f"Archidekt's deck list for '{username}' returned a deck owned by "
                    f"'{owner.get('username', '?')}' instead -- the API's owner filter "
                    f"isn't behaving as expected right now. Stopping rather than risk "
                    f"pulling in unrelated decks. Try --file with explicit deck URLs instead."
                )
            if commander_only and d.get("deckFormat") != 3:
                continue
            ids.append(str(d["id"]))
        if not data.get("next"):
            break
        page += 1
        time.sleep(0.35)
    return ids


def extract_description(deck):
    """Archidekt stores the deck description as Quill Delta JSON (a rich-text
    editor format): {"ops": [{"insert": "some text"}, ...]}. Concatenate the
    plain-text insert fragments; skip non-string inserts (embeds/images)."""
    raw = deck.get("description")
    if not raw:
        return ""
    try:
        delta = json.loads(raw)
        ops = delta.get("ops") or []
    except (TypeError, ValueError):
        return str(raw).strip()  # not JSON -- already plain text, use as-is
    text = "".join(op.get("insert", "") for op in ops if isinstance(op.get("insert"), str))
    return text.strip()


def extract_tags(deck):
    """`deckTags` entries are objects ({"name": "Merfolk", "id": ..., ...}),
    not plain strings -- discovered when this silently changed upstream and
    started crashing render_card()'s tag chips. Defensively also accept plain
    strings, in case this drifts back or differs across API versions."""
    tags = deck.get("deckTags") or []
    names = [t.get("name", "") if isinstance(t, dict) else str(t) for t in tags]
    return [n for n in names if n]


# --------------------------------------------------------------------------- #
# Parsing a deck into the fields we print
# --------------------------------------------------------------------------- #
def extract_info(deck):
    cats = {c["name"]: c for c in deck.get("categories", [])}
    premier = {c["name"] for c in deck.get("categories", []) if c.get("isPremier")}
    excluded = {c["name"] for c in deck.get("categories", [])
                if c.get("includedInDeck") is False}

    commanders = []
    seen_colors, deck_colors = [], set()
    count = 0

    for ac in deck.get("cards", []):
        ccats = ac.get("categories") or []
        qty = ac.get("quantity", 1)
        oracle = (ac.get("card") or {}).get("oracleCard") or {}

        # deck size: skip cards whose only categories are all excluded (sideboard/maybeboard)
        if ccats and all(c in excluded for c in ccats):
            pass
        else:
            count += qty
            for cn in oracle.get("colorIdentity") or []:
                w = COLOR_TO_WUBRG.get(cn)
                if w and w != "C":
                    deck_colors.add(w)

        # commander(s): any card sitting in a premier category
        if premier and any(c in premier for c in ccats):
            name = oracle.get("name", "?")
            ci = [COLOR_TO_WUBRG.get(c) for c in (oracle.get("colorIdentity") or [])]
            commanders.append(name)
            for w in ci:
                if w and w != "C":
                    seen_colors.append(w)

    # Color identity: prefer the commander's; else the whole deck's.
    color_source = set(seen_colors) if commanders else deck_colors
    colors = [w for w in WUBRG_ORDER if w in color_source]
    key = "".join(colors)
    identity = IDENTITY_NAMES.get(key, key or "Colorless")

    price = None
    total = 0.0
    for ac in deck.get("cards", []):
        ccats = ac.get("categories") or []
        if ccats and all(c in excluded for c in ccats):
            continue
        p = ((ac.get("card") or {}).get("prices") or {}).get("tcg")
        if p:
            total += p * ac.get("quantity", 1)
    if total > 0:
        price = total

    return {
        "id": deck.get("id"),
        "name": deck.get("name", "Untitled"),
        "format": FORMAT_NAMES.get(deck.get("deckFormat"), "—"),
        "format_code": deck.get("deckFormat"),
        "bracket": deck.get("edhBracket"),
        "commanders": commanders,
        "colors": colors,               # list like ["W","U"]
        "identity": identity,           # "Azorius"
        "tags": extract_tags(deck),
        "count": count,
        "owner": (deck.get("owner") or {}).get("username", ""),
        "featured": deck.get("featured") or "",
        "price": price,
        "description": extract_description(deck),
    }


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

# Every render_card()/render_html() style choice lives in one options dict so
# CLI flags, GUI checkboxes, and the render code all key off the same names.
DEFAULT_CARD_OPTS = {
    "art_opacity": 0.45,       # 0..1; 0 = no featured-art background at all
    "text_halo": False,        # white glow behind text, for busy art
    "feature": "commander",    # "commander" | "deck" -- which name is the big title
    "show_spine": True,
    "show_pips": True,
    "show_bracket": True,
    "show_tags": True,
    "show_identity": True,
    "show_format": True,
    "show_count": True,
    "show_owner": True,
    "show_price": False,
    "show_description": False,
    "use_qr": True,
}


def card_opts(overrides=None):
    """DEFAULT_CARD_OPTS merged with any provided overrides (missing/None keys
    fall back to the default -- callers can pass a partial dict)."""
    opts = dict(DEFAULT_CARD_OPTS)
    for k, v in (overrides or {}).items():
        if v is not None and k in DEFAULT_CARD_OPTS:
            opts[k] = v
    return opts


def pip_html(colors):
    if not colors:
        colors = ["C"]
    return "".join(f'<span class="pip pip-{w}"></span>' for w in colors)


def pip_css():
    """One background-image rule per WUBRG+C color, keyed by class so the
    embedded SVG data URI appears once in the stylesheet no matter how many
    pips/cards reference it."""
    return "\n  ".join(
        f'.pip-{w} {{ background-image: url("{uri}"); }}'
        for w, uri in PIP_ICON_SVG.items()
    )


def qr_data_uri(url):
    """Return an inline SVG data-URI QR for a URL, or None if segno is absent."""
    if not HAVE_SEGNO:
        return None
    qr = segno.make(url, error="m")
    return qr.svg_data_uri(dark="#141210", light=None, border=2)


def render_card(info, opts=None):
    opts = card_opts(opts)
    commanders = info["commanders"] or ["(no commander set)"]
    cmd = " + ".join(commanders)

    if opts["feature"] == "deck":
        big_text, small_text = info["name"], cmd
    else:
        big_text, small_text = cmd, info["name"]

    art_layer = ""
    if opts["art_opacity"] > 0 and info["featured"]:
        art_layer = (
            f'<div class="art" style="background-image:url(\'{html.escape(info["featured"])}\');'
            f'opacity:{opts["art_opacity"]:.3f}"></div>'
        )

    bracket = ""
    if opts["show_bracket"] and info["bracket"]:
        bname = BRACKET_NAMES.get(info["bracket"], "")
        bracket = (
            f'<div class="bracket"><span class="bnum">{info["bracket"]}</span>'
            f'<span class="blabel">{html.escape(bname)}</span></div>'
        )

    pips = f'<div class="pips">{pip_html(info["colors"])}</div>' if opts["show_pips"] else ""

    tags = ""
    if opts["show_tags"] and info["tags"]:
        chips = "".join(
            f'<span class="chip">{html.escape(t)}</span>' for t in info["tags"][:4]
        )
        tags = f'<div class="tags">{chips}</div>'

    desc = ""
    if opts["show_description"] and info["description"]:
        desc = f'<div class="desc">{html.escape(info["description"])}</div>'

    price = ""
    if opts["show_price"] and info["price"]:
        price = f'<span class="price">~${info["price"]:,.0f}</span>'

    ident = html.escape(info["identity"])
    ckey = "".join(info["colors"])
    ident_line = ident if ident == ckey or not ckey else f"{ident} ({ckey})"

    meta_parts = []
    if opts["show_identity"]:
        meta_parts.append(f'<span class="ident">{ident_line}</span>')
    if opts["show_format"]:
        meta_parts.append(f'<span>{html.escape(info["format"])}</span>')
    if opts["show_count"]:
        meta_parts.append(f'<span>{info["count"]} cards</span>')
    meta_html = '<span class="dot">•</span>'.join(meta_parts)

    spine = ""
    if opts["show_spine"]:
        spine_colors = info["colors"] or ["C"]
        spine_segs = "".join(
            f'<span style="flex:1;background:{PIP_STYLE[w][0]}"></span>' for w in spine_colors
        )
        spine = f'<div class="spine">{spine_segs}</div>'

    url = DECK_URL.format(id=info["id"])
    uri = qr_data_uri(url) if opts["use_qr"] else None
    if uri:
        qr_block = f'<div class="qr"><img src="{uri}" alt="deck QR"></div>'
        qr_caption = f'#{info["id"]}'          # small human-readable fallback
    else:
        qr_block = ""
        qr_caption = f'archidekt.com/decks/{info["id"]}'

    foot_txt_parts = []
    if opts["show_owner"] and info["owner"]:
        foot_txt_parts.append(f'<span>{html.escape(info["owner"])}</span>')
    foot_txt_parts.append(f'<span class="src">{qr_caption}</span>')

    inner_class = "inner halo" if opts["text_halo"] else "inner"

    return f"""
      <div class="card">
        {art_layer}
        {spine}
        <div class="{inner_class}">
          <div class="top">
            {bracket or '<div class="bracket empty"></div>'}
            {pips}
          </div>
          <div class="mid">
            <div class="cmd">{html.escape(big_text)}</div>
            <div class="dname">{html.escape(small_text)}</div>
            {desc}
          </div>
          <div class="bot">
            {tags}
            <div class="meta">
              {meta_html}
              {price}
            </div>
            <div class="foot">
              <div class="foot-txt">
                {"".join(foot_txt_parts)}
              </div>
              {qr_block}
            </div>
          </div>
        </div>
      </div>"""


PAPER = {"letter": (8.5, 11.0), "a4": (8.2677, 11.6929)}   # inches
CARD_W, CARD_H = 2.5, 3.5                                   # true MTG size, inches
SAFE_MARGIN = 0.16                                          # keep clear of printer no-print border


def layout_metrics(paper, gap_mm, card_scale):
    """Return card/gap sizes (inches), clamping the gap so 3x3 still fits the page."""
    pw, ph = PAPER.get(paper, PAPER["letter"])
    cw, ch = CARD_W * card_scale, CARD_H * card_scale
    want = max(0.0, gap_mm) / 25.4
    max_gx = max(0.0, (pw - 2 * SAFE_MARGIN - 3 * cw) / 2)
    max_gy = max(0.0, (ph - 2 * SAFE_MARGIN - 3 * ch) / 2)
    return {
        "pw": pw, "ph": ph, "cw": cw, "ch": ch,
        "gx": min(want, max_gx), "gy": min(want, max_gy),
        "max_gx": max_gx, "max_gy": max_gy, "want": want,
    }


def cropmarks_html(m):
    """Thin dashed guide lines down the center of each interior card gap.

    The gap between columns/rows is empty page background all the way through
    (no card ever overlaps it), so a full-length line at its center is a safe
    straightedge guide for cutting -- effectively extending the cut line
    across the narrow gap instead of leaving it to guesswork.
    """
    grid_w = 3 * m["cw"] + 2 * m["gx"]
    grid_h = 3 * m["ch"] + 2 * m["gy"]
    x0 = (m["pw"] - grid_w) / 2
    y0 = (m["ph"] - grid_h) / 2
    marks = []
    if m["gx"] > 0.0005:
        for i in (1, 2):
            cx = x0 + i * m["cw"] + (i - 0.5) * m["gx"]
            marks.append(
                f'<div class="cropline v" style="left:{cx:.4f}in; top:{y0:.4f}in; height:{grid_h:.4f}in;"></div>'
            )
    if m["gy"] > 0.0005:
        for i in (1, 2):
            cy = y0 + i * m["ch"] + (i - 0.5) * m["gy"]
            marks.append(
                f'<div class="cropline h" style="top:{cy:.4f}in; left:{x0:.4f}in; width:{grid_w:.4f}in;"></div>'
            )
    return "".join(marks)


def card_css(m, page_size):
    """The full card/sheet stylesheet, parameterized by layout_metrics() output.

    Factored out so the GUI's live preview can embed byte-for-byte the same
    CSS as the generated print file -- what you see in the browser preview
    is exactly what render_html() will produce.
    """
    return f"""
  :root {{
    --card-w: {m["cw"]:.4f}in; --card-h: {m["ch"]:.4f}in;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; background: #ecebe7; }}
  body {{ font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; color: #1c1b19; }}

  @page {{ size: {page_size}; margin: 0; }}

  .sheet {{
    position: relative;
    width: {m["pw"]:.4f}in; height: {m["ph"]:.4f}in;
    display: grid;
    grid-template-columns: repeat(3, var(--card-w));
    grid-template-rows: repeat(3, var(--card-h));
    column-gap: {m["gx"]:.4f}in; row-gap: {m["gy"]:.4f}in;
    place-content: center;
    margin: 0 auto;
    background: #fff;
  }}
  @media screen {{ .sheet {{ margin: 18px auto; box-shadow: 0 3px 16px rgba(0,0,0,.16); }} }}
  @media print {{ .sheet {{ break-after: page; background: transparent; box-shadow: none; }} }}

  .cropline {{ position: absolute; pointer-events: none; z-index: 5; }}
  .cropline.v {{ width: 0; border-left: 0.5pt dashed #bab49f; }}
  .cropline.h {{ height: 0; border-top: 0.5pt dashed #bab49f; }}

  .card {{
    position: relative;
    width: var(--card-w); height: var(--card-h);
    overflow: hidden;
    border: 0.6px solid #c9c6bf;         /* cut guide */
    background: #fbfaf6;
    color: #1c1b19;                      /* self-contained: don't rely on inherited
                                             body color, which the GUI's own dark
                                             theme also sets on html/body */
    -webkit-print-color-adjust: exact; print-color-adjust: exact;
  }}
  .art {{
    position: absolute; inset: 0;
    background-size: cover; background-position: center;
    filter: saturate(1.1);                 /* opacity set inline per-card (user-adjustable) */
  }}
  .card::after {{                          /* readability veil */
    content:""; position:absolute; inset:0;
    background: linear-gradient(180deg, rgba(255,255,255,.30), rgba(255,255,255,.55) 55%, rgba(255,255,255,.80));
  }}
  .spine {{
    position: absolute; left: 0; top: 0; bottom: 0; width: 0.11in; z-index: 3;
    display: flex; flex-direction: column;
    border-right: 0.6px solid rgba(0,0,0,.18);
  }}
  .inner {{
    position: relative; z-index: 2;
    height: 100%; padding: 0.16in 0.17in 0.16in calc(0.17in + 0.11in);
    display: flex; flex-direction: column;
  }}

  .top {{ display: flex; align-items: flex-start; justify-content: space-between; }}
  .bracket {{ display: flex; align-items: center; gap: 4px; }}
  .bracket.empty {{ min-height: 22px; }}
  .bnum {{
    width: 22px; height: 22px; border-radius: 6px;
    background: #1c1b19; color: #fff; font-weight: 800;
    display: flex; align-items: center; justify-content: center; font-size: 12px;
  }}
  .blabel {{ font-size: 8px; text-transform: uppercase; letter-spacing: .06em; color: #4a463f; font-weight: 700; }}

  .pips {{ display: flex; gap: 3px; }}
  .pip {{
    width: 17px; height: 17px; border-radius: 50%;
    background-size: cover; background-position: center;
    border: 0.6px solid rgba(0,0,0,.18);
  }}
  {pip_css()}

  .mid {{ flex: 1; display: flex; flex-direction: column; justify-content: center; padding: 6px 0; }}
  .cmd {{
    font-family: Georgia, "Times New Roman", serif;
    font-weight: 700; line-height: 1.05;
    font-size: 15.5px; letter-spacing: -0.2px;
    /* clamp long names */
    display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden;
  }}
  .dname {{ margin-top: 5px; font-size: 9.5px; font-style: italic; color: #46433d;
            display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }}
  .desc {{ margin-top: 4px; font-size: 7.8px; line-height: 1.25; color: #57534a;
           display:-webkit-box; -webkit-line-clamp:6; -webkit-box-orient:vertical; overflow:hidden; }}

  /* text-halo option: a soft white glow behind every letter, so text stays
     readable regardless of what's showing through the art behind it. */
  .halo, .halo * {{
    text-shadow:
      0 0 2px #fff, 0 0 2px #fff, 0 0 2px #fff, 0 0 2px #fff,
      0 0 5px #fff, 0 0 5px #fff, 0 0 8px #fff;
  }}
  /* .bnum is already white-on-solid-black -- a white glow there just
     blurs the number instead of helping it read. */
  .halo .bnum {{ text-shadow: none; }}

  .bot {{ display: flex; flex-direction: column; gap: 5px; }}
  .tags {{ display: flex; flex-wrap: wrap; gap: 3px; }}
  .chip {{
    font-size: 7.5px; font-weight: 700; padding: 1.5px 5px; border-radius: 999px;
    background: rgba(28,27,25,.08); color: #33302b; letter-spacing: .02em;
  }}
  .meta {{ font-size: 8.5px; color: #33302b; display: flex; flex-wrap: wrap; align-items: center; gap: 3px; }}
  .ident {{ font-weight: 800; }}
  .dot {{ color: #a49e93; }}
  .price {{ margin-left: auto; font-weight: 800; }}
  .foot {{
    display: flex; justify-content: space-between; align-items: flex-end;
    border-top: 0.6px solid rgba(0,0,0,.12); padding-top: 4px; gap: 6px;
  }}
  .foot-txt {{
    display: flex; flex-direction: column; gap: 1px;
    font-size: 7px; color: #6b665d; letter-spacing: .02em; min-width: 0;
  }}
  .foot-txt span {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .src {{ font-variant-numeric: tabular-nums; }}
  .qr {{
    flex: none; width: 0.5in; height: 0.5in;
    background: #fff; border-radius: 3px; padding: 2px;
    box-shadow: 0 0 0 0.6px rgba(0,0,0,.12);
  }}
  .qr img {{ width: 100%; height: 100%; display: block; }}

  .note {{ max-width: 7.5in; margin: 16px auto; font-size: 13px; color: #444; }}
  @media print {{ .note {{ display: none; }} }}
"""


def sheets_html(cards, opts, m):
    """Render <div class="sheet">...</div> blocks, 9 cards per sheet."""
    crop_html = cropmarks_html(m)
    sheets = []
    for i in range(0, len(cards), 9):
        chunk = cards[i:i + 9]
        body = "".join(render_card(c, opts) for c in chunk)
        sheets.append(f'<div class="sheet">{crop_html}{body}</div>')
    return "\n".join(sheets)


def render_html(cards, paper="letter", opts=None, gap_mm=3.0, card_scale=1.0):
    opts = card_opts(opts)
    page_size = "A4" if paper == "a4" else "letter"
    m = layout_metrics(paper, gap_mm, card_scale)

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Deck Info Cards</title>
<style>{card_css(m, page_size)}</style></head>
<body>
  <div class="note">
    <strong>{len(cards)} deck card(s).</strong> To print: use your browser's
    Print dialog, choose <em>Save as PDF</em>, set <em>Margins</em> to
    <em>None</em>, and enable <em>Background graphics</em>. Card size:
    {m["cw"]:.2f}&times;{m["ch"]:.2f}in, with a
    {m["gx"]*25.4:.1f}mm&times;{m["gy"]*25.4:.1f}mm gap between cards.
    Cut along the light borders, using the faint dashed guide lines in the
    gaps to keep interior cuts straight.
  </div>
  {sheets_html(cards, opts, m)}
</body></html>"""


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Make Magic-card-sized Archidekt deck info cards.")
    ap.add_argument("tokens", nargs="*", help="Deck IDs or URLs.")
    ap.add_argument("--user", help="Archidekt username: fetch all their PUBLIC decks.")
    ap.add_argument("--file", help="Text file of deck IDs/URLs (one per line).")
    ap.add_argument("--out", default="deck_cards.html", help="Output HTML file.")
    ap.add_argument("--all-formats", action="store_true", help="Include non-Commander decks.")
    ap.add_argument("--a4", action="store_true", help="Lay out for A4 paper.")
    ap.add_argument("--gap", type=float, default=3.0,
                    help="Space between cards in mm (auto-fit to page; default 3).")
    ap.add_argument("--card-scale", type=float, default=1.0,
                    help="Scale cards (e.g. 0.93) to allow larger even gaps. Default 1.0 = true size.")
    ap.add_argument("--gui", action="store_true",
                    help="Launch the local browser GUI instead of running from the command line.")
    ap.add_argument("--port", type=int, default=8765, help="Port for --gui's local server.")

    # Card content/style -- one flag per DEFAULT_CARD_OPTS entry.
    ap.add_argument("--art-opacity", type=float, default=DEFAULT_CARD_OPTS["art_opacity"],
                    help="Featured-art background opacity, 0-1 (default 0.45). 0 disables it.")
    ap.add_argument("--no-art", action="store_true", help="Shorthand for --art-opacity 0.")
    ap.add_argument("--text-halo", action="store_true",
                    help="Add a white glow behind card text for readability over busy art.")
    ap.add_argument("--feature-deck-name", action="store_true",
                    help="Make the deck name the big title instead of the commander(s).")
    ap.add_argument("--no-spine", action="store_true", help="Hide the left-edge color spine.")
    ap.add_argument("--no-pips", action="store_true", help="Hide the WUBRG mana-symbol pips.")
    ap.add_argument("--no-bracket", action="store_true", help="Hide the EDH bracket badge.")
    ap.add_argument("--no-tags", action="store_true", help="Hide deck tags.")
    ap.add_argument("--no-identity", action="store_true", help="Hide the color-identity name.")
    ap.add_argument("--no-format", action="store_true", help="Hide the format.")
    ap.add_argument("--no-count", action="store_true", help="Hide the card count.")
    ap.add_argument("--no-owner", action="store_true", help="Hide the deck owner.")
    ap.add_argument("--price", action="store_true", help="Show approximate TCGplayer price.")
    ap.add_argument("--description", action="store_true", help="Show the deck's Archidekt description.")
    ap.add_argument("--no-qr", action="store_true", help="Use a printed link instead of a QR code.")
    args = ap.parse_args()

    if args.gui:
        import gui_server
        gui_server.run(port=args.port)
        return

    if not args.no_qr and not HAVE_SEGNO:
        print("Note: `segno` isn't installed, so cards will show a printed link "
              "instead of a QR code.\n      Run `pip install segno` and re-run "
              "for QR codes (or pass --no-qr to silence this).\n")

    _m = layout_metrics("a4" if args.a4 else "letter", args.gap, args.card_scale)
    if _m["want"] - _m["gy"] > 0.01 / 25.4:
        print(f"Note: gap limited to ~{_m['gy']*25.4:.1f}mm vertically "
              f"(you asked for {args.gap:.1f}mm) — 9 full-size cards nearly fill the "
              f"page height.\n      For a larger even gap, try --a4 or e.g. "
              f"--card-scale 0.93.\n")

    ids = []
    if args.user:
        print(f"Listing public decks for '{args.user}'...")
        ids += enumerate_user_decks(args.user, commander_only=not args.all_formats)
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            for line in fh:
                line = line.split("#", 1)[0].strip()
                if line:
                    did = parse_deck_id(line)
                    if did:
                        ids.append(did)
    for t in args.tokens:
        did = parse_deck_id(t)
        if did:
            ids.append(did)

    # de-dupe, preserve order
    seen = set()
    ids = [i for i in ids if not (i in seen or seen.add(i))]

    if not ids:
        ap.error("No decks given. Use --user NAME, --file decks.txt, or pass deck IDs/URLs.")

    print(f"Fetching {len(ids)} deck(s)...")
    cards = []
    for n, did in enumerate(ids, 1):
        try:
            deck = fetch_json(API_DECK.format(id=did))
            info = extract_info(deck)
            if not args.all_formats and info["format_code"] != 3:
                print(f"  [{n}/{len(ids)}] skip {did} ({info['format']}, not Commander)")
                continue
            cards.append(info)
            cmd = " + ".join(info["commanders"]) or info["name"]
            print(f"  [{n}/{len(ids)}] {cmd} — {info['identity']}"
                  + (f", Bracket {info['bracket']}" if info["bracket"] else ""))
        except urllib.error.HTTPError as e:
            print(f"  [{n}/{len(ids)}] deck {did}: HTTP {e.code} (private or not found?)")
        except Exception as e:  # noqa
            print(f"  [{n}/{len(ids)}] deck {did}: {e}")
        time.sleep(0.4)

    if not cards:
        raise SystemExit("No usable decks fetched.")

    opts = card_opts({
        "art_opacity": 0.0 if args.no_art else args.art_opacity,
        "text_halo": args.text_halo,
        "feature": "deck" if args.feature_deck_name else "commander",
        "show_spine": not args.no_spine,
        "show_pips": not args.no_pips,
        "show_bracket": not args.no_bracket,
        "show_tags": not args.no_tags,
        "show_identity": not args.no_identity,
        "show_format": not args.no_format,
        "show_count": not args.no_count,
        "show_owner": not args.no_owner,
        "show_price": args.price,
        "show_description": args.description,
        "use_qr": not args.no_qr,
    })
    doc = render_html(
        cards,
        paper="a4" if args.a4 else "letter",
        opts=opts,
        gap_mm=args.gap,
        card_scale=args.card_scale,
    )
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(doc)
    print(f"\nWrote {len(cards)} card(s) -> {args.out}")
    print("Open it in a browser and Print -> Save as PDF (enable Background graphics).")


if __name__ == "__main__":
    main()

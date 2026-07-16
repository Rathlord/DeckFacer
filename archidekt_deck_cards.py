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

# Official-style mana-symbol icons for the WUBRG pips, sourced from a
# reference sprite sheet the user provided (not hand-drawn lookalikes).
# Each is a small (64x64) palette-optimized PNG, ~1KB, embedded as a data URI
# once per color in card_css() -- referenced by class (.pip-W etc.) so the
# encoded bytes appear once per document regardless of how many pips use it,
# not once per <span>.
PIP_ICON_PNG = {
    "W": (
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEAAAABABAMAAABYR2ztAAAAGFBMVEX///////39//7//v78/Of49tqqqpgLDArA3mhIAAADpklEQVR42mWVwW/jRBTGf28cCWelbWacCraVII6XAxyQEnpFiBU3/gv+Qk4cOXNAJdFyQUhNXFZqg9h4xgXahMUeDmM7TjsnZ96Xb75533tvhN76eA7ATzkYRLMChOOVUedR1QMM+tELL5cRL58ve3uPGdr19AgxxcUKLuASG312jXfHDGI8FwZwI3eZ6EVa54+OkPErAJ9Y/Pb1R3nDELVh+fpTAK8+yGN59vxX2AGgWoKxAeBuajVwOmv3I4Bo9uK/VwD483gDwHC0OWK4DjlE6Vb8WLLsoOH2C9Mm0m/igDjJbzsGZbRxR4qAMbrbqpqEe91PzCxqANHF6VcBjQaZdBTVTDQKagQRDUgOJA5vvbVW5ssg0qy/wZ3Ve6A4B7kXdX5+NoThzW6HAsYgGItFO0B7oxGTTSGaMYD0FEAyUy9HvVtYL/PX3cWWiEEFpQ4HFKuccb1EwRsNIZGjUrf/r3OjEXTLEAJJBpCJbndmjkFITWOAtla0yQBxDdmA+Sngw69CEu/X006ohog/PgdidkMolImHQ7+PgU0MyO1OyRiA1SrH32mAxPYuq1v/jLHYNHynDgrtAJkdGXzX+mgprkNWYdDIsyJ1l4QJuVbptgx2zx3gs4mhA4ibeE3S1lDq4M6M07J3WqJ0UxkKrybOT48aU5xMAeMAJbIep6UGyscNrHRo/xFJ8ijU2D4qcYq2jXk6FBIHCmT9BOCA+mcno2B3Q+iPQW/1lTMO5YEc/Mod6s1r4G/MlQgRf6W4M4rdv+/fxS1gf8PDDoabSis8nKx9KVZ1Yt3IrfJQD24AIEUtXksrwv+uaZqZPLhphHLKpKH4M+3Nvs7uBFQdCL7X0mJ/mam+cLN2YBffwng6deHmAyp3sDldF0gWBqkGtu7DgaSH87xk/mj0qlmlYNF102KBwNWRN8ovtg4oNbzVAHXZAfyyWqrQZDYDIgxgtQUHDrbpEgUs4KXusZ7Y4rvOunDNpBc3Tlb5ly4MBVBgK1dYC77EAmqC0TjAchUG6b7U1m4erPCeiiHOY6R8sYl/9IlFgSSVGKORtrg04L32aaNBk3apOAFsU1/bg0hVuUO1+utQ0H6BhDm5v7/95Lemc9wZRUj2bvsuXllQ4GG5tS1DIAD7Wh8eFAGbxADPRqthkPDPzfr2ANDvHkoTg0/u9yH+w0Z6L44HqoUDGYUD7DZzT1/e07mWWgDs5aEfowPgobge7WPw7pL2UTx63L2leNqm/wOOBHCy15jQRgAAAABJRU5ErkJggg=="
    ),
    "U": (
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEAAAABABAMAAABYR2ztAAAAGFBMVEX///////39///X5vHC2OnB1+m/1uciJykf3qGFAAADbklEQVR42m2V0Y/bRBDGfzs5oVxRz7MJEhXSJY77gECqSq78+/wJ5Q4qEDzUdVKptIjLbnKi5zvpPDx47dgt+2TPfjvzzXwzu47BKryXxZt4XbW/Hou4wb40SE5JAWUPOBkAGgqabUHa/5+Vp0hF++29cvTgTJpt4RSLTQUivrUfQxQ4na2AMkgpGIQRQKv1bNWUQMGDXi1jsk+68x/WL+z2Pc5P/wqTJXUNNYCkDMv1vIkoFsA3hws/9uBvn35jkWkEnuynjjv9eK/udFojgNO9PF0CDpDtErCbF9rWUAAkv1hAS/t8tQGwuVZ65OAuNimmvNI9AMHnkdgCTOelJk6P15Y+J4olD7J5TnJQvE3bFrK1j6lQi5OY/PKwBkvObrRoKgTY5iFaTAxoko+A70i6jgDn66H6vmkBuuo75pUOAPEwA04QKWCWRSDroc5bxLQEAb/srFsFZN+hbKUgNA5oOe4/6bCtgiCzmCI//oEkyGBNWD2C+hSL94eWwhenNbTdMHVBqLKuZdNZOx73FSIuT5aH1NTzzTHTBUKeokong4s9wIF0pJz17J715RLyE1xUA1j0DT6/VHAe8P/spOnM+/6c6+tRgeQe8OC2R/J9DKWSqiPsj4BBHsfJOh/MuWsGd0LeVXeo9PN+IBHadnRvRwIcZZO+aMdti27RW2VQtH5dYcdapSxsSMHwVXKgIrscIMsHgDNk34ZsVEbRUzsvcW1SDUgzcp4mItI2icZKBBs3SatFG1GdCtWGMG7EqiNt5hCWDsLIxSHr06kQ2NknZXh2pV0NcoQYP2X51Y8Q3wAxooJZBRyqAUJBHcQmgjShwvvPqvGrgS0pK0GyQwSy0b41QPGmVdN2KHY2LqYC1a5p5Q4aIRvFCAp2/gswwU2Z2Cl3fw7l+qOmvivfRxAaC9c5uGykN04tWHtXT+/4cgpf3097wE4jtcWsvUgj9jojHi6PDraAhv62lydMplNb9i5+XhHdx3fOYguwmMXvav7ePWoR1wer6/xlFWL/Xhx0r9H87/4UbLdd1nH224fbYTMXFIDf7ZUwP4v54fq1lKM36/Zuvox3s1WU7y0ij18KYQg4de+4+TbehuJs8+Tg/n0pENxoXgqcv0hCXIaoUDodv922+0k9EGy30c/Hv1ps89dFAJpK1EpJ0vwHE2poLS7F7GQAAAAASUVORK5CYII="
    ),
    "B": (
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEAAAABABAMAAABYR2ztAAAAGFBMVEX//////v////3+/v7Oysa6sqx+eXULDQsDQNFJAAADAUlEQVR42nWVX2/bNhTFf5cyBudhCSmjQzugnZS+zp0cf4L1ew/9AnPqxduAAYOlABvWPcxikwFJO0jcAymKSmI+6B8P7z338FxKSMbaALTdliOjYrFek1XpN0lfFgXdrmJzLMCwdF09ESGrYKNWGFp3mVVEHhLnu6sLbQCcbTfrzSMO1W5VDs+u/eHi8gHgdfNWJ5kP9WnIoXyGdf29BgfiYXmxMx4w87fuwoAYA+SutZAvBWdjBHYlSOkXSW5AXl8VPjgA3307RyJHTrRFvvpcRw7ZzxpMqo6GnCpyWD57KGpukbNDiJCpf/XAPioB5LdZSPHGgNE2BexFIy+rANgViJYUcFClgcU2AFZgoE8SqBIBqQpQqKUBjeh6UgQF8qUGRXmrEaA8m7BAYLEDhbv2GkjuHgIEyCi/1rzwAk61cPcye/5B0eupMePw6ipu9BGLCuQ7VHbNkQgCQqUQ0IBr00kbcmAzd2E4mePqD/dxP119Zw3c3csXd6ryEVq0i0rV4BofYXCUs8OFILpX/lQrj/MEAo0m0JDBk5K6YLhiQcNWJazDzSVoVaiRwgCY1Isalzx5IoQqJo60TwB8KTjtgLMhkIsAS240kGuHJQcQUyS9aTXGf28XDjkfc/V6NqqG35vRMNansF78IbG18RQBLGoL4PZt1MiG6doCbGfUhVenLRM7tgG2RWVDyD6p/zA8Z4WKOkoi8cdx91QX+0V4JHtbNYpX07aeAHpQ3KaL5HzSBDdNNaORsVGkxCsaKGxfbdVohsejBRT9ccA/RYOiHC3koLfJ6xWg2O9joS24pNJ2OKM2bVgek/lSWhtMq95P/Bb756fBUX3XBBUs0H8MUtRv9vu+8UfxpY1mdg1pAO/JbunN4VzYMgvUy/ejq28OFpwVt7eDZQ6TPw7swQ0ucHtw7yqbtJGiUKvJCff7TdhYH6HvdV9P5nfxbxvuf+tfTmQ+SPjH7puhibN4PJtfr+d8mtPe//Xnfy9/0wEwG+Oen/5IVtFt1Yqub0Lr/Q+ywSqblYmY6wAAAABJRU5ErkJggg=="
    ),
    "R": (
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEAAAABABAMAAABYR2ztAAAAGFBMVEX///////39//7uybfim3rhmHd9V0YMDQuQ7nJWAAADw0lEQVR42m2VTW/bRhCGn1kLlZgC5iwDJFYK1BRzaZtTjP6S/uicGhQ9FQVqUb7ENtBwZ32oqbbh9EBKpprMZXdn3p2d7xUmCt/uQh0BTy0NwBaABU80bGlIKYZ6xpwDiJogMmz5AoVadILFOV+Om3ieaYAtaZPP7aE+saE2tdxEUYje7STIwY6z6X64+7ppin4FRRGlu78QYpoB/n5xdnVhPX3f71d5HdN+KTwBNlb+c1Xm+GwdI0uTx0o/3Gl+PACCkt+8zJtn66IoYlwl9ur7Xo4A0f2b2jA39iukKFK0V60n7SeA9uGKfaO3j8lWBRSr25gvfr/sD4B+/4Psm7jqi+IxPVtBsbwvi6/uDCCAaFWXlSIlKAZQueRKDnGQ9Tey/x543Htu1gBysfPo+36MpD786GeAm1SvIXVhgyCiLqWxQLwBhS5lNdGuFY8qlzelB/XJBrImb029u75uReMOKg/5UkcjgyLDzgUPGnNTJnMQFW92BgEVXFtSKdB4FWspHVCrRWPUAG9NhlzuskqXm5rABiBazDUQwoODqOPmsRUAcUBcUEXCoKoOokA6N0hl3gCCeNhBULGp7tyQhCeoAEpUFRZs4qxAO0/E9i1ARA0I8xL2JCmqDUwAagg7Pan+aKLaTgozeAingOQgyaaTIgH3lI4cB3PTbZrOxv8UIFFtk3RrgFAJAZGDaGy69FqnrnFAj80rZSJJ9NSoizMpHmRxaE7PDXRJmohHG7k6KAsgJtwfroCYIuD6SYCxs8LB5bdTdACbViAcAGUz82THaMJY9j4qmHnr8FwBz46N80HKs5mCTg+rQwoGHL0C8Jtpc0O2QcNnL3Q+hQBnwMJg80kF3Y2O8FYzKKHG8FlRpDILwJB9Q6oIZqBPL3iWMo7ABwViKMekzCjXgO/yZih3EEKLzdN9aRVAVzVqHhgWeHly//mZAh42cDMAi53bac3oVBwMdMBi2OToXxreJPfzLYFd62ZfkPtNeWMQkDRl/n/yrXZmcIYuQyHrz/R/EOuWVWJBLnd1PhVCSlKe/+wGiyj+0Zh70rVA9PynJCDgqEn7JP/UxhgjnLfD8UP55aeZlUFIIPybHeCsgNKKi4fjG7KOr4ok5+8uDGCRkFi/j/OM4knlj2zHUUy/vP/ufv0kvrX9X78t+yNgRfDwMlNA6vvbdFcUy3eHHB968z314TsVxa9znU4AWrbjeBwfuf5Vh9m32Per2/ziFllNNnxoL25N5j9vTIhLVUcgDW0uDeKYwsUh+k78OKr1h81gh+bmPwbCxW4JS+vHAAAAAElFTkSuQmCC"
    ),
    "G": (
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEAAAABABAMAAABYR2ztAAAAGFBMVEX///////39//7d59ekwZZ9knMNEQ8KDQzE4+PIAAADVklEQVR42nWVO3fjNhCFv4F8zlIujAE352S9hUMyVbo8/v9f8CZliiVlF7GbEIALGy6iSQHRovxAJXEuZgZz7wWE4xoCgM271Tdk/QfXsT8JnwJaZe9g5IPVLpW69zMMY2gVmCf6ZOkNoGMTFIA4Z5/iG4D7Lbwkm9Ox1c0hLL8f42ztSdMJwO3/UECGUANb/rYTwE+fL2t8u20q4r9AOQJk8wvAzz6V0j4VgPBnUwEOEO0BxCeQ1EsIIL+uSsh5D/AZAHXNV20SzV1NsQHC0EhoylcASgmxtE9FPt0sJZxTGYYh+EPSCKmHto7tDK5+IPgo/YoAE5DOEuCQWyUkTNKKoazQukOJHvEgcZ0BBbmoAB9AFDuh3oJC6AAnTsHSOhqAhx7aXe3hXfWY0yohpwEsnwYPMpCrDhwKYu+kOFR1QUH0VVQUFNqboXc3wEu8/kggmgcQObAZlkMkQKq0NHfgmRwwLCzILMicah4fEKN1PeJPDmHjUc8d6hSppSWo9UuPFmPKCntxcBCwH3Md2iu7Ll1JjJNmD4SslpajqoNodbaDogmke53BiFUkXQJozScAq7N0CxOKJSKYR3QRgCOcLTOUUMcvSS5u/WH8RnTgfIAcxzHXSv5bVCySu0OJkOo546QAOobaTD3vGSgaUcI8ZYC960lKyqbEShYJiLHVCEjuIz5GjyRIaXOurjEoocmXu64gIWm8u4vnfvtPecRt3Jftl6agk/NZmwLPfrwvkLeP99whLhJJisUx+8rKmAD28wRpZw4sSw4RG3MG8OnFopbBXcCkOu/Aoi6aXun7TJPux8pG7MKpg8xIzoBYfWkZWHt47sDdTqstKZ2UeABct9qR7I13ontl3BOAAs74EDDXO5jpowS37MCxv0qnzlvWfj/C4EamerNLaD1gLSsfwhm4GUB6qimlj1W0f/nDRSpXrkGGsI3bApRWuKQwb0tTCA709hqCxRgsIBBlkIDdjEfddZseoO1jMElonBP/xt3Lbc9NlUC0iXnyNknPvEscAabTgb2UYt7P42Q7lfWLU37MAShFIonC0/fn+6asH7WHixyg8AQUbJLH51NAL6NIs8x4gk+pOHvpAdi779d1QHG+PjyaA69ffm2HYUDaDtcte/8HLeZ7F/SpRPoAAAAASUVORK5CYII="
    ),
    "C": (
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEAAAABABAMAAABYR2ztAAAAGFBMVEX///////3+/v7W0c66s6y6squ4satNSUduHGytAAADs0lEQVR42oWVT3PbNhDFf4A8GSkHEaAPSdwxTVE9ZTpprE/QTj9/bTWXXhoKoi/NIcJSF0udBNsDSFmeZFpc+AcPu293H3YnjMuUrwSA8g0Hnn6fXmqRhXEQ09apfAtYbBp/WaeJpk3cdekEmAzPZrP88a1rnU391ZW86P1sdjgHlI8/LGvwm1KPj5/eko4MRGx2lMrfEkSpHc64drlUN5jOgJvJMlkUuuyvXTZbf8bB9j+9EDhgDm8ezYHjm90iPe71ZKFq3oECYkBAcd0qpJOLpms6jAccuOw8PayMGwAmNVWdHe6GzEQh3TozAvZNN1B29VPiH/L7BabwVR+9RoBL0GLrAK2utz6CtTWX2zHm2gF24QGV7Ty7MPufB8M2daCn6tjGAZa0QIb95hYuUpv3JS0EuIByWwDGFxMHcGnbZiDqioClm2v+7Ib0+1UoRAU6Z8Gqr/PG7vYU4rscc7EKWOt8ZqVLIA4F6moApa7VulIAjDj4+hH0Hqiy2Lb02D47kAnohwWQBMqcWjt3TI6/HAFelVN2Xl+SXrYvp+aFE2YcH/+eWj+WAe1AgGYDQ0BOBkVhOkg1gA2xEmznQdICZ4cgDAg65DjkmgNutDCvRz2aDKxOos1R4lBiNuZilf+A6YNlvGXpJj8VkLztuRnvRTYfOVsWjad78R/r4nR9xXqSOxPMaMiNSeGJw3PA/7hI8fmp9OyAYDPLCiwRJLtyQ/AKdleM6PAszIFrbcUAiGCSDudMOHEzYlUB9gHel9m9mU8gAMapOPsU3CQYwG7p3qMouH3A2Ng5IFWjEmG+GLVBrLFOjAO/X0PZOiB1DtYbEXAKdp4CgF6DWQVgfwtqHKBpDzZItrxfg1mB+RXY1YDpCwFrNwQAroHcdfjaBUD9RsCmm6G92PsxR/ohtyTZObAkqcF7RzUi7mrbe6DqtW2ts59HMWeEfm5GSwHvJ9NPcnmYznIK/7ziy7oEPU5n0/7jIXeYKi5OPUow4/lUCWAuYPvwnogpspRRybXsvgiAFfT6j1Ee+/AknLQpYow7C3S/+2+l1qU+jL06Xa+Lc5VlBu18kD3QPTj1zySdui9d9TQv9KZfTc1sejCvZ2oOYPqv96/C2cTp23WmngCMSrWL4XwkcfPXHe3GOxCY76u7bWObs6k3O6gc3vqW6T8qfTm/W79GXDyRxEeb7igbgNJ93IzN+HzylvNt4zw2Rd2FJoVvZ7cvNjRAxMztdwDgzTxgHEbVBb4DMIWAqeV5p/kXzEOVKd6luhsAAAAASUVORK5CYII="
    ),
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
        "tags": deck.get("deckTags") or [],
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
    embedded PNG data URI appears once in the stylesheet no matter how many
    pips/cards reference it."""
    return "\n  ".join(
        f'.pip-{w} {{ background-image: url("{uri}"); }}'
        for w, uri in PIP_ICON_PNG.items()
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
           display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }}

  /* text-halo option: a soft white glow behind every letter, so text stays
     readable regardless of what's showing through the art behind it. */
  .halo, .halo * {{
    text-shadow:
      0 0 2px #fff, 0 0 2px #fff, 0 0 2px #fff, 0 0 2px #fff,
      0 0 5px #fff, 0 0 5px #fff, 0 0 8px #fff;
  }}

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

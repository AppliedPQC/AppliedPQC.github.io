#!/usr/bin/env python3
"""Generate the icon and share image into pages/static/.

These are committed rather than built in CI: the runner has no browser, and a
share image that regenerates on every deploy would churn the repository for no
reason. Running this by hand after a brand change keeps them reproducible
instead of being binaries nobody can rebuild.

    python3 -m pip install playwright && python3 -m playwright install chromium
    python3 pages/make_brand_assets.py

Writes favicon.svg (drawn here, no browser needed) plus icon-180.png,
icon-512.png and og.png, rasterised through headless Chromium.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")

NAVY_A = "#16293a"
NAVY_B = "#0a141d"
TEAL = "#3fdbd3"
SITE = "appliedpqc.io"
TAGLINE = "Post-quantum cryptography, from lattices to byte-exact FIPS code"

FONT = ('-apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", '
        'Helvetica, Arial, sans-serif')

# The logo is a wordmark with no separate symbol, so the icon takes the one
# letter that carries it: the Q of PQC, whose straight tail is the mark's most
# distinctive stroke. "PQC" set across a 16px tile would be a smudge.
FAVICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="%s"/>
      <stop offset="1" stop-color="%s"/>
    </linearGradient>
  </defs>
  <rect width="64" height="64" rx="14" fill="url(#bg)"/>
  <circle cx="32" cy="31" r="15" fill="none" stroke="%s" stroke-width="8.5"/>
  <path d="M33 33 L47 47" stroke="%s" stroke-width="8.5" stroke-linecap="square"/>
</svg>
""" % (NAVY_A, NAVY_B, TEAL, TEAL)


def og_html():
    """The 1200x630 share card: the wordmark on the logo's navy field."""
    return """<!doctype html><meta charset="utf-8"><style>
  * { margin: 0; box-sizing: border-box; }
  body { width: 1200px; height: 630px; font-family: %s; overflow: hidden; }
  .card {
    width: 1200px; height: 630px; position: relative;
    background:
      radial-gradient(120%% 90%% at 50%% -10%%, #24425c 0%%, rgba(36,66,92,0) 60%%),
      linear-gradient(150deg, %s 0%%, %s 100%%);
    display: flex; flex-direction: column;
    align-items: center; justify-content: center; gap: 26px;
  }
  .mark { font-size: 128px; font-weight: 700; letter-spacing: -.045em; color: #fff; line-height: 1; }
  .mark span { color: %s; }
  .tag { font-size: 30px; color: #9fb3c4; letter-spacing: -.01em; text-align: center; max-width: 900px; }
  .rule { width: 96px; height: 5px; border-radius: 3px; background: %s; opacity: .9; }
  .host { position: absolute; bottom: 46px; font-size: 24px; color: #6f8598; letter-spacing: .02em; }
</style>
<div class="card">
  <div class="mark">Applied <span>PQC</span></div>
  <div class="rule"></div>
  <div class="tag">%s</div>
  <div class="host">%s</div>
</div>
""" % (FONT, NAVY_A, NAVY_B, TEAL, TEAL, TAGLINE, SITE)


def icon_html(px):
    """The SVG icon at a fixed pixel size, for the raster fallbacks."""
    return ('<!doctype html><meta charset="utf-8">'
            '<style>*{margin:0}body{width:%dpx;height:%dpx;overflow:hidden}'
            'svg{display:block;width:%dpx;height:%dpx}</style>%s'
            % (px, px, px, px, FAVICON))


def main():
    os.makedirs(STATIC, exist_ok=True)
    with open(os.path.join(STATIC, "favicon.svg"), "w") as f:
        f.write(FAVICON)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("favicon.svg written. Install playwright for the "
                         "raster assets: pip install playwright && "
                         "playwright install chromium")

    jobs = [("og.png", og_html(), 1200, 630),
            ("icon-180.png", icon_html(180), 180, 180),
            ("icon-512.png", icon_html(512), 512, 512)]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for name, html, w, h in jobs:
            page = browser.new_page(viewport={"width": w, "height": h},
                                    device_scale_factor=1)
            page.set_content(html)
            page.wait_for_timeout(200)
            page.screenshot(path=os.path.join(STATIC, name))
            print("wrote static/%s (%dx%d)" % (name, w, h))
        browser.close()


if __name__ == "__main__":
    main()

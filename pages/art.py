"""Generated cover art for the card grid.

The site has no photographs and no illustrator, but a wall of bare text cards
reads as a list rather than a gallery. These tiles fill that gap without
pretending to be decoration: each one draws the actual object its card is
about -- a lattice with its basis, a Merkle tree of one-time keys, the butterfly
network of an NTT, a discrete Gaussian over the integers.

Everything is inline SVG, so there are no image requests, nothing to optimise
and nothing to go stale. Each tile carries its own colour, which is why the art
does not need light and dark variants: the tile supplies its background and the
marks are drawn on top in white.

Geometry is drawn from ``random.Random(seed)`` with the seed fixed per card, so
a given card renders identically on every build and the generated HTML diffs
cleanly.
"""

import math
import random
import zlib

# Hues far enough apart to read as distinct at thumbnail size. Index into this
# by card, so a page of cards is varied without any of them being chosen twice.
HUES = [262, 210, 155, 24, 340, 190, 46, 288]

W, H = 400, 260


def _shell(hue, body, seed):
    """Wrap ``body`` in a tile with a two-stop wash of ``hue``."""
    a, b = hue, (hue + 38) % 360
    return (
        '<svg class="art" viewBox="0 0 %d %d" role="img" aria-hidden="true" '
        'preserveAspectRatio="xMidYMid slice">'
        '<defs><linearGradient id="g%s" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="hsl(%d 72%% 58%%)"/>'
        '<stop offset="1" stop-color="hsl(%d 68%% 44%%)"/>'
        '</linearGradient></defs>'
        '<rect width="%d" height="%d" fill="url(#g%s)"/>%s</svg>'
    ) % (W, H, seed, a, b, W, H, seed, body)


def _lattice(rnd):
    """A 2-D lattice with its basis vectors -- chapters on lattices, ML-KEM.

    The basis is deliberately skew: a lattice drawn on a square grid looks like
    graph paper, and the whole point of the hard problems is that the basis is
    not orthogonal.
    """
    ox, oy = 150, 128
    v1 = (74, -26)
    v2 = (30, 60)
    lo1, hi1, lo2, hi2 = -4, 5, -3, 4

    def pt(i, j):
        return ox + i * v1[0] + j * v2[0], oy + i * v1[1] + j * v2[1]

    out = []
    # Rules along both basis directions first: without them the points read as
    # scattered stars rather than as a lattice.
    for j in range(lo2, hi2 + 1):
        x1, y1 = pt(lo1, j)
        x2, y2 = pt(hi1, j)
        out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#fff" '
                   'stroke-width="1.1" stroke-opacity=".34"/>' % (x1, y1, x2, y2))
    for i in range(lo1, hi1 + 1):
        x1, y1 = pt(i, lo2)
        x2, y2 = pt(i, hi2)
        out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#fff" '
                   'stroke-width="1.1" stroke-opacity=".34"/>' % (x1, y1, x2, y2))
    for i in range(lo1, hi1 + 1):
        for j in range(lo2, hi2 + 1):
            x, y = pt(i, j)
            if -10 < x < W + 10 and -10 < y < H + 10:
                out.append('<circle cx="%.1f" cy="%.1f" r="4.4" fill="#fff" '
                           'fill-opacity=".92"/>' % (x, y))
    # The fundamental cell, so the two vectors read as a basis rather than as
    # two stray lines.
    out.append('<path d="M%d %d l%d %d l%d %d l%d %d Z" fill="#fff" '
               'fill-opacity=".3"/>'
               % (ox, oy, v1[0], v1[1], v2[0], v2[1], -v1[0], -v1[1]))
    for v in (v1, v2):
        out.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#fff" '
                   'stroke-width="4" stroke-opacity="1" stroke-linecap="round"/>'
                   % (ox, oy, ox + v[0], oy + v[1]))
    out.append('<circle cx="%d" cy="%d" r="6.5" fill="#fff"/>' % (ox, oy))
    return "".join(out)


def _merkle(rnd):
    """A hash tree over one-time keys -- SLH-DSA, and the Winternitz sections."""
    out = []
    levels = 4
    top_y, gap = 46, 56
    for lvl in range(levels):
        n = 2 ** lvl
        y = top_y + lvl * gap
        span = W / (n + 1)
        for i in range(n):
            x = span * (i + 1)
            if lvl:
                py = top_y + (lvl - 1) * gap
                pspan = W / (2 ** (lvl - 1) + 1)
                px = pspan * (i // 2 + 1)
                out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" '
                           'stroke="#fff" stroke-width="1.6" stroke-opacity=".55"/>'
                           % (px, py + 9, x, y - 9))
            r = 9 if lvl == 0 else 7 - lvl * 0.7
            op = ".95" if lvl == 0 else ".78"
            out.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="#fff" '
                       'fill-opacity="%s"/>' % (x, y, r, op))
    return "".join(out)


def _ntt(rnd):
    """A butterfly network -- the NTT chapter, and ML-DSA's inner loop."""
    out = []
    cols, rows = 4, 6
    x0, dx = 52, 98
    y0, dy = 34, 38
    for c in range(cols - 1):
        step = 2 ** c
        for r in range(rows):
            partner = r ^ step if (r ^ step) < rows else r
            out.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#fff" '
                       'stroke-width="1.5" stroke-opacity=".5"/>'
                       % (x0 + c * dx, y0 + r * dy,
                          x0 + (c + 1) * dx, y0 + partner * dy))
    for c in range(cols):
        for r in range(rows):
            out.append('<circle cx="%d" cy="%d" r="4.6" fill="#fff" '
                       'fill-opacity=".9"/>' % (x0 + c * dx, y0 + r * dy))
    return "".join(out)


def _gaussian(rnd):
    """A discrete Gaussian over the integers -- Falcon's sampler, FN-DSA."""
    out = []
    base, sigma, scale = 214, 52.0, 150.0
    for i in range(21):
        x = 20 + i * 18
        d = (x - W / 2) / sigma
        h = math.exp(-0.5 * d * d) * scale
        out.append('<rect x="%.1f" y="%.1f" width="12" height="%.1f" rx="3" '
                   'fill="#fff" fill-opacity=".85"/>' % (x, base - h, h))
    pts = []
    for i in range(61):
        x = 14 + i * 6.2
        d = (x - W / 2) / sigma
        pts.append("%.1f,%.1f" % (x, base - math.exp(-0.5 * d * d) * scale))
    out.append('<polyline points="%s" fill="none" stroke="#fff" '
               'stroke-width="2.6" stroke-opacity=".95" stroke-linecap="round"/>'
               % " ".join(pts))
    out.append('<line x1="10" y1="%d" x2="%d" y2="%d" stroke="#fff" '
               'stroke-width="2" stroke-opacity=".6"/>' % (base, W - 10, base))
    return "".join(out)


def _book(rnd):
    """Stacked spreads -- the book itself."""
    out = []
    for i, (dx, dy, op) in enumerate(((26, 40, ".35"), (13, 26, ".55"), (0, 12, ".95"))):
        out.append('<rect x="%d" y="%d" width="228" height="176" rx="12" '
                   'fill="#fff" fill-opacity="%s"/>' % (86 - dx, 42 + dy - 12, op))
    for i in range(7):
        y = 74 + i * 18
        w = 150 if i % 3 else 104
        out.append('<rect x="106" y="%d" width="%d" height="6" rx="3" '
                   'fill="hsl(0 0%% 25%% / .28)"/>' % (y, w))
    return "".join(out)


def _code(rnd):
    """A terminal with a prompt -- the runnable playground."""
    out = ['<rect x="52" y="46" width="296" height="168" rx="14" fill="#fff" '
           'fill-opacity=".95"/>',
           '<rect x="52" y="46" width="296" height="30" rx="14" '
           'fill="hsl(0 0% 20% / .12)"/>']
    for i, cx in enumerate((72, 90, 108)):
        out.append('<circle cx="%d" cy="61" r="4.4" fill="hsl(0 0%% 20%% / .3)"/>' % cx)
    rows = ((0, 34), (1, 92), (2, 66), (3, 118), (4, 54))
    for i, w in rows:
        y = 94 + i * 21
        out.append('<rect x="72" y="%d" width="12" height="7" rx="3.5" '
                   'fill="hsl(0 0%% 25%% / .45)"/>' % y)
        out.append('<rect x="92" y="%d" width="%d" height="7" rx="3.5" '
                   'fill="hsl(0 0%% 25%% / .26)"/>' % (y, w))
    return "".join(out)


def _list(rnd):
    """A checked list -- awesome-pqc, which is link-verified."""
    out = []
    for i in range(5):
        y = 58 + i * 32
        out.append('<rect x="64" y="%d" width="24" height="24" rx="8" fill="#fff" '
                   'fill-opacity=".92"/>' % y)
        out.append('<polyline points="%d,%d %d,%d %d,%d" fill="none" '
                   'stroke="hsl(0 0%% 22%% / .55)" stroke-width="3" '
                   'stroke-linecap="round" stroke-linejoin="round"/>'
                   % (70, y + 12, 75, y + 17, 82, y + 7))
        out.append('<rect x="102" y="%d" width="%d" height="9" rx="4.5" '
                   'fill="#fff" fill-opacity=".7"/>' % (y + 7, 150 + (i % 3) * 44))
    return "".join(out)


def _post(rnd):
    """Layered surfaces over a curve -- research posts."""
    out = []
    for i in range(3):
        out.append('<rect x="%d" y="%d" width="250" height="46" rx="12" '
                   'fill="#fff" fill-opacity="%s"/>'
                   % (46 + i * 18, 46 + i * 54, (".4", ".62", ".9")[i]))
    pts = " ".join("%.1f,%.1f" % (30 + i * 21,
                                  212 - 46 * math.sin(i / 2.4) - i * 1.6)
                   for i in range(18))
    out.append('<polyline points="%s" fill="none" stroke="#fff" '
               'stroke-width="3" stroke-opacity=".95" stroke-linecap="round" '
               'stroke-linejoin="round"/>' % pts)
    return "".join(out)


KINDS = {
    "lattice": _lattice,
    "merkle": _merkle,
    "ntt": _ntt,
    "gaussian": _gaussian,
    "book": _book,
    "code": _code,
    "list": _list,
    "post": _post,
}


def tile(kind, i=0):
    """Return an inline SVG tile of ``kind``, coloured by position ``i``."""
    draw = KINDS.get(kind)
    if draw is None:
        raise KeyError("unknown art kind %r; have %s"
                       % (kind, ", ".join(sorted(KINDS))))
    seed = "%s%d" % (kind, i)
    # crc32 rather than hash(): str hashing is salted per process, and the
    # gradient id must be identical on every build or the HTML churns.
    uid = zlib.crc32(seed.encode()) % 99991
    return _shell(HUES[i % len(HUES)], draw(random.Random(seed)), uid)

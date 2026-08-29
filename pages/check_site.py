#!/usr/bin/env python3
"""
Assert the rendered site is actually what it should be.

A broken page usually still deploys: pandoc exits 0 on mangled input, a failed
fetch can leave a stub, and a mistake in a shared partial removes the chrome
from every page at once. Each check here corresponds to something that has
genuinely gone wrong at least once.

Usage::

    python3 pages/check_site.py --source ../AppliedPQC site/
"""

import argparse
import glob
import json
import os
import re
import sys

# Filled in from --source: the checkout of the book repository.
LISTINGS = None
# The blog is this site's own content, beside pages/.
POSTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "blog")

failures = []
notes = []


def check(ok, message):
    if not ok:
        failures.append(message)


def read(path):
    return open(path, encoding="utf-8", errors="replace").read()


def main():
    global LISTINGS
    ap = argparse.ArgumentParser(description="Check a rendered site.")
    ap.add_argument("site", help="the rendered site directory")
    ap.add_argument("--source", required=True,
                    help="checkout of AppliedPQC/AppliedPQC")
    args = ap.parse_args()
    root = os.path.abspath(args.source)
    LISTINGS = os.path.join(root, "sage", "playground", "book_listings.json")
    site = os.path.abspath(args.site)
    p = lambda *a: os.path.join(site, *a)

    # --- the book itself --------------------------------------------------
    check(os.path.getsize(p("apqc.pdf")) > 100_000, "apqc.pdf missing or truncated")

    # The author list is structured data, so it has no visible rendering and a
    # wrong one is invisible until it reaches a search result. It was wrong.
    book_tex = os.path.join(root, "apqc.tex")
    if os.path.exists(book_tex):
        m = re.search(r"\\author\{(.*?)\}", read(book_tex), re.S)
        if m:
            expected = [n.strip() for n in re.split(r"\\and", m.group(1)) if n.strip()]
            rendered = read(p("index.html"))
            for name in expected:
                check(name in rendered,
                      "landing page structured data omits the author %s" % name)
            notes.append("authors: %s" % ", ".join(expected))

    # --- landing page -----------------------------------------------------
    index = read(p("index.html"))
    check("<title>Applied PQC:" in index, "landing page lost its title")
    check('href="apqc.pdf"' in index, "landing page does not link the PDF")
    check('<main class="home">' in index, "landing page is not using the home layout")
    check(len(re.findall(r'<section class="band', index)) >= 2,
          "landing page has fewer than two section bands")
    # The grid is the landing page. Every entry must carry cover art and a
    # stretched link, or the card is a dead tile.
    cards = re.findall(r'<li class="card"', index)
    check(len(cards) >= 8, "landing page has fewer than eight cards")
    check(index.count('class="art"') >= len(cards),
          "a landing-page card is missing its cover art")
    check(index.count('class="stretch"') >= len(cards),
          "a landing-page card is missing its link")
    check('data-filter=' in index and 'data-pills=' in index,
          "landing page lost the card filter")
    check("AppliedPQC/awesome-pqc" in index, "landing page does not surface awesome-pqc")
    # The site is about getting post-quantum cryptography deployed, and the book
    # is one of the things it publishes towards that. Both of these have been
    # the book's own blurb before now, and the drift is silent: the page still
    # builds and still looks right, it just says the site is a book again.
    # The Book node in the JSON-LD is *supposed* to carry the book's blurb, so
    # this looks at the two places that describe the site itself.
    check('name="description" content="A book that builds' not in index,
          "landing page's meta description is the book's, not the site's")
    check(re.search(r'<p class="lede">\s*A book\b', index) is None,
          "landing page opens by calling itself a book rather than the site")
    check('data-cat="deploy"' in index,
          "landing page lost the deploy shelf")
    check("bitcoin-stark-verifier" in index,
          "landing page does not surface bitcoin-stark-verifier")
    # The page count is read from the build, never typed in; if the source it
    # comes from moves, the book card loses it silently.
    check(re.search(r"<span>[0-9]+ pages</span>", index) is not None,
          "landing page lost the page count")
    check(index.count('name="viewport"') == 1, "landing page has a duplicate viewport tag")

    # --- playground -------------------------------------------------------
    play = read(p("playground.html"))
    check("embedded_sagecell.js" in play, "playground lost the Sage Cell embed")
    cells = play.count('type="text/x-sage"')
    check(cells >= 8, "playground rendered only %d cells" % cells)
    check(play.count("sage/playground.py") >= 8, "playground cells lost their bootstrap")
    check("playground-01_sagemath_basics.html" in play,
          "playground lost the chapter table")
    # The custom pandoc template exists to keep pandoc's own stylesheet out.
    check("max-width: 36em" not in play, "pandoc's default stylesheet leaked in")
    # book-code.html was published before the pages merged.
    check("url=playground.html" in read(p("book-code.html")),
          "the old book-code URL no longer redirects")

    # --- chapter pages ----------------------------------------------------
    chapter_pages = sorted(glob.glob(p("playground-*.html")))
    data = json.load(open(LISTINGS))
    expected = sum(1 for c in data["chapters"] for l in c["listings"] if l["runnable"])
    book_cells = sum(read(f).count('type="text/x-sage"') for f in chapter_pages)
    check(book_cells == expected,
          "%d book cells rendered, expected %d" % (book_cells, expected))
    # A shredded cell shows up as book code leaking into a paragraph.
    for f in chapter_pages:
        check(re.search(r"<p>[a-z_]+ = ", read(f)) is None,
              "%s: a listing was mangled out of its cell" % os.path.basename(f))

    # --- blog -------------------------------------------------------------
    blog = read(p("blog.html"))
    local = [f for f in glob.glob(os.path.join(POSTS, "*.md"))
             if os.path.basename(f) != "README.md"]
    sources_path = os.path.join(POSTS, "sources.json")
    sourced = json.load(open(sources_path)) if os.path.exists(sources_path) else []
    built = glob.glob(p("blog-*.html"))
    check(len(built) == len(local) + len(sourced),
          "%d blog pages built, expected %d local + %d sourced"
          % (len(built), len(local), len(sourced)))
    for f in local:
        slug = os.path.basename(f)[:-3]
        check("blog-%s.html" % slug in blog, "blog index does not link %s" % slug)
    for e in sourced:
        page = p("blog-%s.html" % e["slug"])
        check(os.path.exists(page), "sourced post %s was not built" % e["slug"])
        if os.path.exists(page):
            html = read(page)
            # A failed fetch would leave a stub rather than an error.
            check(len(html) > 8000,
                  "%s is only %d bytes; the source fetch looks empty"
                  % (os.path.basename(page), len(html)))
            check("Originally published" in html and e["repo"] in html,
                  "%s lost its link back to the source" % os.path.basename(page))
            # A long post gets a contents block, generated by pandoc from the
            # headings. If --toc stops being passed the page still renders and
            # simply loses its navigation, which is easy not to notice.
            heads = html.count("<h2")
            if heads >= 6:
                entries = len(re.findall(r'<li><a href="#', html))
                check('<aside class="toc"' in html and entries >= heads,
                      "%s has %d sections but no usable contents sidebar"
                      % (os.path.basename(page), heads))
                # The sidebar only works if the body sits in the other column;
                # without the wrapper the text renders under a 15rem gap.
                check('class="layout-toc"' in html and "<article>" in html,
                      "%s has a contents sidebar but no two-column wrapper"
                      % os.path.basename(page))
                notes.append("%s: contents sidebar, %d entries" % (e["slug"], entries))
            # Sourced documents are Markdown from another repository, and
            # nothing stops one arriving with TeX in it. The pandoc call has no
            # math engine, so a dollar-delimited span renders as literal
            # backslashes -- which looks like a typo rather than a failure, and
            # in the one document sourced here the affected section was the one
            # whose argument turns on reading a formula.
            leaked = re.findall(r"\\(?:mathsf|mathrm|mathbb|cdot|oplus|leq|gets|pi_|alpha|beta|gamma|delta)",
                                html)
            check(not leaked,
                  "%s renders raw TeX (%s); the pandoc call has no math engine, "
                  "so the source should not use dollar-delimited math"
                  % (os.path.basename(page), ", ".join(sorted(set(leaked))[:3])))

            # Diagrams come from the sourced document as fenced mermaid blocks.
            # If the fence stops being recognised they degrade to plain code
            # blocks, which looks fine and conveys nothing.
            diagrams = html.count('<pre class="mermaid">')
            if diagrams:
                check("mermaid.esm" in html,
                      "%s has %d diagrams but never loads mermaid"
                      % (os.path.basename(page), diagrams))
                notes.append("%s: %d diagram(s)" % (e["slug"], diagrams))
            check("blog-%s.html" % e["slug"] in blog,
                  "blog index does not link %s" % e["slug"])
            notes.append("sourced post %s: %d bytes" % (e["slug"], len(html)))

    # --- chrome, which lives in shared partials ---------------------------
    pages = [f for f in glob.glob(p("*.html")) if "book-code" not in f]
    for f in pages:
        h = read(f)
        name = os.path.basename(f)
        check("x.com/AppliedPQC" in h, "%s has no X link" % name)
        check('class="sitefooter"' in h, "%s has no footer" % name)
        check('class="button" href="apqc.pdf">Download the PDF' not in h,
              "%s: the PDF button is back in the topbar" % name)

    # --- SEO: metadata must be per-page, and everything discoverable --------
    import json as _json
    descs, canons = {}, {}
    for f in pages:
        h, name = read(f), os.path.basename(f)
        d = re.search(r'name="description" content="(.*?)"', h, re.S)
        c = re.search(r'rel="canonical" href="(.*?)"', h, re.S)
        check(d and d.group(1).strip(), "%s has no description" % name)
        check(c and c.group(1).startswith("https://"), "%s has no canonical URL" % name)
        if d: descs.setdefault(d.group(1), []).append(name)
        if c: canons.setdefault(c.group(1), []).append(name)
    for text, where in descs.items():
        check(len(where) == 1,
              "%d pages share one description (%s)" % (len(where), ", ".join(where[:3])))
    for url, where in canons.items():
        check(len(where) == 1,
              "%d pages claim the same canonical URL %s" % (len(where), url))

    # --- brand assets and SEO --------------------------------------------
    for asset in ("favicon.svg", "icon-180.png", "icon-512.png", "og.png",
                  "site.webmanifest"):
        check(os.path.exists(p(asset)), "missing %s" % asset)
    # A share card that 404s is worse than none: the crawler caches the miss.
    if os.path.exists(p("og.png")):
        check(os.path.getsize(p("og.png")) > 10_000, "og.png is truncated")
    check('property="og:image"' in index, "landing page has no og:image")
    check('content="summary_large_image"' in index,
          "landing page is not using the large share card")
    check('rel="icon"' in index, "landing page links no icon")
    check(re.search(r"<title>[^<]{25,90}</title>", index) is not None,
          "landing page title is missing or a bad length for search results")

    # The Run button takes its colours from --btn-primary. A literal label
    # colour once went white-on-white against it and the button disappeared,
    # so assert the token pair that is defined to contrast instead.
    play = read(p("playground.html"))
    btn = re.search(r"\.sagecell_evalButton\s*\{[^}]*\}", play)
    check(btn is not None, "playground lost the Run button styling")
    if btn:
        check("var(--accent-fg)" in btn.group(0),
              "Run button label is not theme-aware; it will vanish in one scheme")
        check(not re.search(r"color:\s*#", btn.group(0)),
              "Run button label uses a literal colour instead of a token")

    # The feed is how this audience subscribes, and a page that does not
    # advertise it is a feed nobody finds.
    check(os.path.exists(p("feed.xml")), "no feed.xml")
    if os.path.exists(p("feed.xml")):
        import xml.etree.ElementTree as FT
        try:
            FT.parse(p("feed.xml"))
        except Exception as exc:                       # noqa: BLE001
            check(False, "feed.xml is not well-formed: %s" % exc)
    check('type="application/atom+xml"' in index, "landing page does not advertise the feed")

    # Figures must be served from this domain: a sourced document writes them
    # as absolute raw.githubusercontent URLs and the build rewrites them.
    for name in os.listdir(site):
        if name.startswith("blog-") and name.endswith(".html"):
            check("raw.githubusercontent.com" not in read(p(name)),
                  "%s still links a figure off-site" % name)

    check(os.path.exists(p("robots.txt")), "no robots.txt")
    check(os.path.exists(p("sitemap.xml")), "no sitemap.xml")
    if os.path.exists(p("sitemap.xml")):
        import xml.etree.ElementTree as ET
        try:
            root = ET.parse(p("sitemap.xml")).getroot()
        except ET.ParseError as e:
            root = None
            failures.append("sitemap.xml is not valid XML: %s" % e)
        if root is not None:
            ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            listed = {u.find("s:loc", ns).text.rsplit("/", 1)[1] or "index.html"
                      for u in root}
            missing = {os.path.basename(f) for f in pages} - listed
            check(not missing, "sitemap omits %s" % ", ".join(sorted(missing)[:3]))
            notes.append("sitemap: %d urls" % len(listed))
    # Structured data must parse; a malformed block is silently ignored by
    # crawlers, which is the same as not having it.
    for f in pages:
        for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>',
                                read(f), re.S):
            try:
                _json.loads(block)
            except ValueError as e:
                failures.append("%s has invalid JSON-LD: %s" % (os.path.basename(f), e))

    notes.append("landing page %d bytes, PDF %d bytes"
                 % (len(index), os.path.getsize(p("apqc.pdf"))))
    notes.append("playground %d cells; book %d chapters, %d cells"
                 % (cells, len(chapter_pages), book_cells))
    notes.append("blog %d post(s); chrome checked on %d pages" % (len(built), len(pages)))

    for n in notes:
        print(n)
    if failures:
        for f in failures:
            print("::error::%s" % f)
        return 1
    print("all site checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

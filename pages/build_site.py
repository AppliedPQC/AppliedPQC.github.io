#!/usr/bin/env python3
"""
Build the whole site: landing page, playground, chapter pages, and the blog.

Everything the site needs is produced here, so the workflow is one command.
There are two kinds of page and each is built the way it should be:

* **Generated pages** -- the landing page and the 18 chapter pages -- come from
  Jinja templates in ``templates/``. Their content is structural (hero, card
  grids, one Sage cell per listing), and putting book code through a Markdown
  parser is what silently shredded a quarter of the cells before: CommonMark
  ends a raw-HTML block at the first blank line, and a quarter of the listings
  contain one.

* **Prose pages** -- the playground text and the blog posts -- are Markdown,
  rendered by pandoc, so footnotes, tables and smart quotes work normally.

Both share one definition of the chrome: ``templates/pandoc.html`` is a Jinja
template that renders *to* a pandoc template, so the topbar and footer exist
once rather than in two copies that drift.

Nothing that could go stale is typed in. Listing and chapter counts come from
``book_listings.json`` (itself generated from ``chapters/*.tex``), the page
count from the built PDF, and the posts from ``blog/`` beside this directory.

The book itself lives in another repository, so its checkout is passed in::

    python3 pages/build_site.py --source ../AppliedPQC site/
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request

import art

from jinja2 import Environment, FileSystemLoader, StrictUndefined

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(HERE, "templates")
STYLES = os.path.join(HERE, "styles")
# The blog is this site's own content, so it sits beside pages/ rather than in
# the book checkout.
POSTS = os.path.join(os.path.dirname(HERE), "blog")
SOURCES = os.path.join(POSTS, "sources.json")

# Filled in from --source: the checkout of the book repository, which supplies
# the PDF and the listing data generated from its chapters.
ROOT = None
LISTINGS = None


def set_source(root):
    global ROOT, LISTINGS
    ROOT = os.path.abspath(root)
    LISTINGS = os.path.join(ROOT, "sage", "playground", "book_listings.json")

GH = "https://github.com/AppliedPQC"
SITE = "https://appliedpqc.io"

BRAND = "Applied PQC"
# Search results truncate around sixty characters, so the suffix is the short
# brand rather than the full book title, and the home page leads with what the
# site is instead of repeating the name twice.
HOME_TITLE = "Applied PQC — where post-quantum cryptography actually stands"
STATIC = os.path.join(HERE, "static")

# The site is about getting post-quantum cryptography deployed; the book is one
# of the things it publishes towards that. SITE_DESC is what the home page and
# the search engines get, BOOK_DESC only describes the book itself.
SITE_DESC = ("NIST has finished; the internet has not. Where post-quantum "
             "cryptography actually stands — what has shipped, what is still a "
             "draft, and what breaks when you deploy it — with byte-exact "
             "implementations of all four standards.")

BOOK_DESC = ("A book that builds post-quantum cryptography from the ground up, from "
             "lattices and Learning With Errors to byte-exact implementations of "
             "ML-KEM, ML-DSA, SLH-DSA and FN-DSA, and on to deployment.")
RAW = "https://raw.githubusercontent.com/AppliedPQC/AppliedPQC/main/sage/playground.py"
BOOT = ('import urllib.request\n'
        'exec(urllib.request.urlopen("%s").read())' % RAW)

STANDARDS = [
    dict(name="ML-KEM", fips="FIPS 203", art="lattice",
         blurb="21 of 21 algorithms. Key encapsulation at 512, 768 and 1024."),
    dict(name="ML-DSA", fips="FIPS 204", art="ntt",
         blurb="49 of 49 algorithms. Signatures at 44, 65 and 87."),
    dict(name="SLH-DSA", fips="FIPS 205", art="merkle",
         blurb="25 of 25 algorithms, all twelve approved parameter sets."),
    dict(name="FN-DSA", fips="FIPS 206", art="gaussian",
         blurb="18 of 18 Falcon algorithms. Still in development at NIST, so "
               "validated against Falcon's own tests."),
]

env = Environment(loader=FileSystemLoader(TEMPLATES),
                  undefined=StrictUndefined,   # a typo'd variable fails the build
                  keep_trailing_newline=True)
# Cards draw their own cover art rather than loading images; see pages/art.py.
env.globals["art"] = art.tile


# Chapters get the drawing of whatever they are about, matched on the stem and
# falling back to the book tile so a new chapter never breaks the build.
CHAPTER_ART = (
    ("lattice", "lattice"), ("lll", "lattice"), ("svp", "lattice"),
    ("lwe", "lattice"), ("module", "lattice"), ("kyber", "lattice"),
    ("ntt", "ntt"), ("polynomial", "ntt"), ("circulant", "ntt"),
    ("convolution", "ntt"), ("dilithium", "ntt"),
    ("hash", "merkle"), ("sphincs", "merkle"), ("merkle", "merkle"),
    ("winternitz", "merkle"), ("slh", "merkle"),
    ("falcon", "gaussian"), ("gaussian", "gaussian"), ("sampl", "gaussian"),
    ("linear", "code"), ("basics", "code"), ("sage", "code"),
)


def chapter_art(stem):
    low = stem.lower()
    for key, kind in CHAPTER_ART:
        if key in low:
            return kind
    return "book"


def css(*names):
    return "\n".join(open(os.path.join(STYLES, n)).read() for n in names)


def pdf_pages(pdf):
    """Page count of the book, so the figure on the landing page is never typed.

    Read from the LaTeX log first: it is always present after a build and needs
    no extra tool. pdfinfo is a fallback for building the site without
    rebuilding the PDF -- it is not installed on the CI runner, and counting
    /Type /Page in the raw bytes does not work because those objects sit inside
    compressed object streams.
    """
    log = os.path.join(ROOT, "apqc.log")
    if os.path.exists(log):
        m = re.search(r"Output written on .*?\((\d+) pages",
                      open(log, errors="replace").read())
        if m:
            return int(m.group(1))
    try:
        out = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True).stdout
        m = re.search(r"^Pages:\s+(\d+)", out, re.M)
        if m:
            return int(m.group(1))
    except FileNotFoundError:
        pass
    return None


AUTHOR = re.compile(r"\\author\{(.*?)\}", re.S)


def authors():
    """The book's authors, read from its title page.

    Typed here, this list goes stale the moment the book gains an author -- and
    silently, because structured data has no visible rendering. It is the one
    piece of the landing page that was not derived from the source, and it was
    wrong: the book had three authors and the site named two.
    """
    m = AUTHOR.search(open(os.path.join(ROOT, "apqc.tex"), errors="replace").read())
    if not m:
        raise SystemExit("apqc.tex has no \\author{...}; the site takes the "
                         "author list from the book's title page")
    names = [n.strip() for n in re.split(r"\\and", m.group(1)) if n.strip()]
    if not names:
        raise SystemExit("apqc.tex has an empty \\author{...}")
    return [{"@type": "Person", "name": n} for n in names]


FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)
RAW_REPO = "https://raw.githubusercontent.com/AppliedPQC/%s/main/%s"


def fetch_sourced(build):
    """Posts whose text lives in another repository.

    The document is fetched at build time rather than copied here, so the
    original stays the single source and the two cannot drift. Its own top-level
    heading becomes the title; only the date and the index summary are held
    locally, since those are about presentation rather than content.
    """
    if not os.path.exists(SOURCES):
        return []
    out = []
    for e in json.load(open(SOURCES)):
        url = RAW_REPO % (e["repo"], e["path"])
        try:
            body = urllib.request.urlopen(url, timeout=30).read().decode()
        except Exception as exc:                       # noqa: BLE001 - reported as-is
            raise SystemExit("could not fetch %s\n%s\nThe blog sources a "
                             "document from another repository; check it is "
                             "still at that path." % (url, exc))
        m = re.search(r"^#\s+(.+)", body, re.M)
        if not m:
            raise SystemExit("%s has no top-level heading to use as a title" % url)
        title = m.group(1).strip()
        home = "https://github.com/AppliedPQC/%s" % e["repo"]
        note = ("*Originally published in [%s](%s/blob/main/%s), where it is "
                "maintained. This page renders that document.*\n\n"
                % (e["repo"], home, e["path"]))
        # Keep the heading first so the page leads with the title, then the note.
        body = body.replace(m.group(0), m.group(0) + "\n\n" + note, 1)
        path = os.path.join(build, "sourced-%s.md" % e["slug"])
        open(path, "w").write(body)
        out.append(dict(title=title, date=e["date"], summary=e.get("summary", ""),
                        slug=e["slug"], path=path, source=home,
                        cat=e.get("cat", "research")))
    return out


def read_posts():
    """Posts written in this repository."""
    if not os.path.isdir(POSTS):
        return []
    out = []
    for f in sorted(os.listdir(POSTS)):
        if not f.endswith(".md") or f == "README.md":
            continue
        path = os.path.join(POSTS, f)
        m = FRONT.match(open(path).read())
        if not m:
            raise SystemExit("%s: missing the --- metadata block at the top" % path)
        meta = {}
        for line in m.group(1).split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        for required in ("title", "date"):
            if not meta.get(required):
                raise SystemExit("%s: metadata block has no %s" % (path, required))
        meta.setdefault("summary", "")
        meta["slug"] = f[:-3]
        meta["path"] = path
        out.append(meta)
    out.sort(key=lambda p: p["date"], reverse=True)
    return out


# A contents block earns its place on a long post and clutters a short one.
TOC_MIN_SECTIONS = 6


def pandoc(src, out, template, title, toc=False, description="", page="",
           ogtype="article", header=None):
    cmd = ["pandoc", src, "--from=gfm+yaml_metadata_block", "--to=html5",
           "--standalone", "--template=" + template,
           "--variable=pagetitle=" + title, "--variable=lang=en",
           "--variable=description=" + description,
           "--variable=page=" + page, "--variable=ogtype=" + ogtype,
           "--output=" + out]
    if toc:
        cmd += ["--toc", "--toc-depth=2"]
    # Raw, because --variable would escape the JSON-LD into nonsense.
    if header:
        cmd += ["--include-in-header=" + header]
    subprocess.run(cmd, check=True)


def wants_toc(path):
    """True when a post has enough top-level sections to be worth navigating."""
    n = len(re.findall(r"^##? ", open(path).read(), re.M))
    return n >= TOC_MIN_SECTIONS


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("dest", help="directory to write the site into")
    ap.add_argument("--source", required=True,
                    help="checkout of AppliedPQC/AppliedPQC")
    args = ap.parse_args()
    set_source(args.source)
    dest = os.path.abspath(args.dest)
    build = os.path.join(dest, "_build")
    os.makedirs(build, exist_ok=True)

    data = json.load(open(LISTINGS))
    chapters = data["chapters"]
    for c in chapters:
        c["art"] = chapter_art(c["stem"])
    n_listings = sum(len(c["listings"]) for c in chapters)
    posts = read_posts() + fetch_sourced(build)
    posts.sort(key=lambda p: p["date"], reverse=True)

    # Icon, share image and their raster fallbacks. Committed rather than
    # generated here; see pages/make_brand_assets.py.
    for name in sorted(os.listdir(STATIC)):
        shutil.copyfile(os.path.join(STATIC, name), os.path.join(dest, name))

    # The book, and the alias some published links still use.
    for name in ("apqc.pdf", "main.pdf"):
        shutil.copyfile(os.path.join(ROOT, "apqc.pdf"), os.path.join(dest, name))
    pages = pdf_pages(os.path.join(dest, "apqc.pdf"))

    who = authors()
    base = dict(gh=GH, site=SITE, css=css("site.css"))

    # --- landing page -----------------------------------------------------
    book_ld = json.dumps({"@context": "https://schema.org", "@graph": [{
        "@type": "WebSite", "@id": SITE + "/#website",
        "name": BRAND, "alternateName": "Applied Post-Quantum Cryptography",
        "url": SITE + "/", "description": SITE_DESC, "inLanguage": "en",
        "publisher": {"@id": SITE + "/#org"},
    }, {
        "@type": "Organization", "@id": SITE + "/#org",
        "name": BRAND, "url": SITE + "/",
        "logo": {"@type": "ImageObject", "url": SITE + "/icon-512.png",
                 "width": 512, "height": 512},
        "sameAs": ["https://x.com/AppliedPQC", GH],
    }, {
        "@type": "Book",
        "name": "Applied Post-Quantum Cryptography",
        "author": who,
        "description": BOOK_DESC, "inLanguage": "en",
        "url": SITE + "/", "isAccessibleForFree": True,
        "numberOfPages": pages,
        "workExample": {"@type": "Book", "bookFormat": "https://schema.org/EBook",
                        "encodingFormat": "application/pdf",
                        "url": SITE + "/apqc.pdf"},
        "publisher": {"@id": SITE + "/#org"},
    }]}, separators=(",", ":"))
    open(os.path.join(dest, "index.html"), "w").write(
        env.get_template("home.html").render(
            base, title=HOME_TITLE,
            css=css("site.css", "home.css"), main_class="home", here="home",
            n_listings=n_listings, pages=pages, posts=posts,
            standards=STANDARDS, description=SITE_DESC, page="",
            og_type="website", og_title=HOME_TITLE,
            jsonld=book_ld))

    # --- chapter pages ----------------------------------------------------
    tpl = env.get_template("chapter.html")
    for c in chapters:
        n_run = sum(1 for l in c["listings"] if l["runnable"])
        page = "playground-%s.html" % c["stem"]
        open(os.path.join(dest, page), "w").write(
            tpl.render(base, title="%s — %s" % (c["title"], BRAND),
                       css=css("site.css", "playground.css"), main_class="",
                       here="playground", chapter=c, boot=BOOT, n_runnable=n_run,
                       description="Every code listing from %s, runnable in your "
                                   "browser: %d snippets, nothing to install."
                                   % (c["title"], n_run),
                       page=page, og_type="article",
                       og_title=c["title"], jsonld=None))
    # book-code.html was a published URL before the pages merged.
    open(os.path.join(dest, "book-code.html"), "w").write(
        env.get_template("redirect.html").render(to="playground.html"))

    # --- prose pages, via pandoc -----------------------------------------
    # One pandoc template per chrome variant, rendered from the same partials
    # the generated pages use.
    def pandoc_template(name, sagecell, extra_css, here, mermaid=False):
        p = os.path.join(build, name)
        open(p, "w").write(env.get_template("pandoc.html").render(
            base, css=css("site.css", *extra_css), sagecell=sagecell,
            mermaid=mermaid, here=here))
        return p

    play_tpl = pandoc_template("t-playground.html", True, ("playground.css",), "playground")
    # Mermaid is only loaded if a post actually contains a diagram, so the blog
    # does not pull a large module for nothing.
    any_diagram = any("```mermaid" in open(p["path"]).read() for p in posts)
    blog_tpl = pandoc_template("t-blog.html", False, (), "blog", mermaid=any_diagram)

    # The playground is the single entry point for running code, so the
    # generated chapter table is appended to its prose.
    table = env.get_template("chapters_table.md").render(
        chapters=chapters, n_listings=n_listings)
    merged = os.path.join(build, "playground.md")
    open(merged, "w").write(open(os.path.join(HERE, "playground.md")).read() + table)
    pandoc(merged, os.path.join(dest, "playground.html"), play_tpl,
           "Playground — %s" % BRAND,
           description="Run all %d code listings from the book and the four NIST "
                       "reference implementations in your browser. Nothing to "
                       "install." % n_listings,
           page="playground.html", ogtype="website")

    for p in posts:
        page_url = "%s/blog-%s.html" % (SITE, p["slug"])
        post_ld = json.dumps({
            "@context": "https://schema.org", "@type": "BlogPosting",
            "headline": p["title"], "datePublished": p["date"],
            "dateModified": p["date"], "inLanguage": "en",
            "description": p.get("summary") or SITE_DESC,
            "url": page_url, "image": SITE + "/og.png",
            "mainEntityOfPage": {"@type": "WebPage", "@id": page_url},
            "author": who,
            "publisher": {"@id": SITE + "/#org"},
            "isAccessibleForFree": True,
        }, separators=(",", ":"))
        ld_file = os.path.join(build, "ld-%s.html" % p["slug"])
        open(ld_file, "w").write(
            '<script type="application/ld+json">%s</script>\n' % post_ld)
        pandoc(p["path"], os.path.join(dest, "blog-%s.html" % p["slug"]), blog_tpl,
               "%s — %s" % (p["title"], BRAND),
               toc=wants_toc(p["path"]),
               description=p.get("summary") or SITE_DESC,
               page="blog-%s.html" % p["slug"], ogtype="article",
               header=ld_file)
    index_md = os.path.join(build, "blog.md")
    open(index_md, "w").write(env.get_template("blog_index.md").render(posts=posts))
    pandoc(index_md, os.path.join(dest, "blog.html"), blog_tpl,
           "Blog — %s" % BRAND,
           description="Notes and research from the Applied PQC project on "
                       "post-quantum migration.",
           page="blog.html", ogtype="website")

    # Sitemap and robots, built from the files actually written rather than a
    # hand-kept list, so a new page cannot be left undiscoverable.
    urls = sorted(f for f in os.listdir(dest)
                  if f.endswith(".html") and f != "book-code.html")
    # lastmod only where a real date exists. Stamping every page with today's
    # date is the classic way to teach a crawler to ignore the field.
    post_dates = {"blog-%s.html" % q["slug"]: q["date"] for q in posts}
    entries = []
    for f in urls:
        loc = SITE + "/" + ("" if f == "index.html" else f)
        prio = "1.0" if f == "index.html" else (
            "0.8" if f in ("playground.html", "blog.html") or f.startswith("blog-")
            else "0.6")
        mod = ("<lastmod>%s</lastmod>" % post_dates[f]) if f in post_dates else ""
        entries.append("  <url><loc>%s</loc>%s<priority>%s</priority></url>"
                       % (loc, mod, prio))
    open(os.path.join(dest, "sitemap.xml"), "w").write(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(entries) + "\n</urlset>\n")
    open(os.path.join(dest, "site.webmanifest"), "w").write(json.dumps({
        "name": "Applied PQC",
        "short_name": "Applied PQC",
        "description": SITE_DESC,
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0e1c28",
        "theme_color": "#0e1c28",
        "icons": [
            {"src": "/favicon.svg", "sizes": "any", "type": "image/svg+xml"},
            {"src": "/icon-180.png", "sizes": "180x180", "type": "image/png"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }, indent=1) + "\n")

    open(os.path.join(dest, "robots.txt"), "w").write(
        "User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % SITE)

    open(os.path.join(dest, ".nojekyll"), "w").close()
    shutil.rmtree(build)

    print("landing page: %d listings, %d chapters, %s"
          % (n_listings, len(chapters), "%d pages" % pages if pages else "no PDF"))
    print("chapter pages: %d" % len(chapters))
    print("blog: %d post(s)" % len(posts))


if __name__ == "__main__":
    main()

import json
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
CSL = os.path.join(HERE, "book.csl")

DRAWN = ("tikzpicture", "algorithmic", "protocol")
VERBATIM = ("lstlisting", "verbatim")

COMMENTS_REPO = "AppliedPQC/AppliedPQC"
COMMENTS_LABEL = "book-comment"


def strip_comments(tex):
    out, verb = [], None
    for line in tex.split("\n"):
        if verb:
            out.append(line)
            if "\\end{%s}" % verb in line:
                verb = None
            continue
        m = re.search(r"\\begin\{(%s)\}" % "|".join(VERBATIM), line)
        if m and "\\end{%s}" % m.group(1) not in line:
            verb = m.group(1)
        cut = re.search(r"(?<!\\)(?:\\\\)*%", line)
        if cut:
            if not line[:cut.start()].strip():
                continue
            line = line[:cut.end() - 1]
        out.append(line)
    return "\n".join(out)


def verbatim_spans(tex):
    return [(m.start(), m.end()) for m in re.finditer(
        r"\\begin\{(%s)\}.*?\\end\{\1\}" % "|".join(VERBATIM), tex, re.S)]


def drawn_spans(tex):
    skip = verbatim_spans(tex)
    spans, depth, start = [], 0, None
    for m in re.finditer(r"\\(begin|end)\{(%s)\}" % "|".join(DRAWN), tex):
        if any(a <= m.start() < b for a, b in skip):
            continue
        if m.group(1) == "begin":
            if depth == 0:
                start = m.start()
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                spans.append((start, m.end()))
    if depth:
        raise SystemExit("unbalanced %s environment" % "/".join(DRAWN))
    return spans


def splice(tex, spans, fn):
    out, at = [], 0
    for i, (a, b) in enumerate(spans):
        out.append(tex[at:a])
        out.append(fn(i, tex[a:b]))
        at = b
    out.append(tex[at:])
    return "".join(out)


def book_order(root):
    main = strip_comments(open(os.path.join(root, "apqc.tex")).read())
    body = main.split("\\begin{document}", 1)[1]
    return re.findall(r"\\input\{chapters/([^}]+)\}", body)


def parse_toc(root, stems):
    toc = open(os.path.join(root, "apqc.toc"), errors="replace").read()
    entry = re.compile(r"^\\contentsline \{(\w+)\}\{(.*)\}\{[^{}]*\}\{[^{}]*\}%?$", re.M)
    items, chapters = [], []
    for m in entry.finditer(toc):
        kind, text = m.group(1), m.group(2)
        num = re.match(r"\\numberline \{([^{}]*)\}(.*)", text)
        if kind == "part":
            p = re.match(r"(\w+)\\hspace \{1em\}(.*)", text)
            items.append(dict(kind="part", num=p.group(1) if p else "",
                              title=tex_text(p.group(2) if p else text)))
        elif kind == "chapter" and num and not num.group(1):
            items.append(dict(kind="subpart", title=tex_text(num.group(2))))
        elif kind == "chapter" and num:
            if len(chapters) == len(stems):
                raise SystemExit("apqc.toc lists more chapters than apqc.tex inputs")
            c = dict(kind="chapter", num=num.group(1), title=tex_text(num.group(2)),
                     stem=stems[len(chapters)], sections=[], subsections=[])
            chapters.append(c)
            items.append(c)
        elif kind in ("section", "subsection") and num and chapters:
            chapters[-1][kind + "s"].append(num.group(1))
    if len(chapters) != len(stems):
        raise SystemExit("apqc.toc has %d chapters but apqc.tex inputs %d; rebuild "
                         "the PDF first" % (len(chapters), len(stems)))
    return items, chapters


def tex_text(s):
    s = re.sub(r"\\(?:emph|textit|textbf|texttt|textsc|textsuperscript)\s*\{([^{}]*)\}",
               r"\1", s)
    s = re.sub(r"\\[a-zA-Z]+\s*", "", s)
    s = s.replace("---", "\u2014").replace("--", "\u2013").replace("~", "\u00a0")
    s = s.replace("\\&", "&").replace("``", "\u201c").replace("''", "\u201d")
    return re.sub(r"\s+", " ", s.replace("{", "").replace("}", "")).strip()


def parse_aux(root):
    aux = open(os.path.join(root, "apqc.aux"), errors="replace").read()
    labels = {}
    for m in re.finditer(r"^\\newlabel\{([^{}]+)\}\{\{(.*?)\}\{", aux, re.M):
        labels[m.group(1)] = m.group(2)
    floats = {}
    for kind, ext in (("figure", "lof"), ("table", "lot"), ("algorithm", "loa")):
        floats[kind] = re.findall(
            r"^\\@writefile\{%s\}\{\\contentsline \{%s\}\{\\numberline \{([^{}]*)\}"
            % (ext, kind), aux, re.M)
    return labels, floats


def slug(stem):
    return "book-" + re.sub(r"^\d+_", "", stem).replace("_", "-")


def render_drawn(root, work, chapters, sources):
    figdir = os.path.join(work, "drawn")
    os.makedirs(os.path.join(figdir, "chapters"), exist_ok=True)
    names, total = {}, 0
    for c in chapters:
        tex = sources[c["stem"]]
        spans = drawn_spans(tex)
        names[c["stem"]] = ["%s-%d.svg" % (slug(c["stem"]), i + 1)
                            for i in range(len(spans))]
        total += len(spans)
        wrapped = splice(tex, spans,
                         lambda i, s: "\\begin{preview}%s\\end{preview}" % s)
        open(os.path.join(figdir, "chapters", c["stem"] + ".tex"), "w").write(wrapped)

    main = open(os.path.join(root, "apqc.tex")).read()
    main = main.replace("\\begin{document}",
                        "\\usepackage[active,tightpage]{preview}\n"
                        "\\setlength{\\PreviewBorder}{3pt}\n"
                        "\\begin{document}", 1)
    open(os.path.join(figdir, "drawn.tex"), "w").write(main)
    for ext in ("aux", "bbl"):
        src = os.path.join(root, "apqc." + ext)
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(figdir, "drawn." + ext))
    texinputs = os.pathsep.join([figdir, root, ""])
    run = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "drawn.tex"],
        cwd=figdir, env=dict(os.environ, TEXINPUTS=texinputs),
        capture_output=True, text=True)
    pdf = os.path.join(figdir, "drawn.pdf")
    if run.returncode != 0 or not os.path.exists(pdf):
        raise SystemExit("typesetting the book's figures failed:\n" + run.stdout[-3000:])
    m = re.search(r"Output written on .*?\((\d+) pages?", run.stdout)
    pages = int(m.group(1)) if m else 0
    if pages != total:
        raise SystemExit("the figure build produced %d pages for %d drawn blocks"
                         % (pages, total))
    if not shutil.which("pdftocairo"):
        raise SystemExit("pdftocairo (poppler-utils) is needed to convert the "
                         "book's figures to SVG")

    jobs, n = [], 0
    for c in chapters:
        for name in names[c["stem"]]:
            n += 1
            jobs.append((n, os.path.join(figdir, name)))

    def convert(job):
        page, out = job
        subprocess.run(["pdftocairo", "-svg", "-f", str(page), "-l", str(page),
                        pdf, out], check=True)

    with ThreadPoolExecutor(max_workers=os.cpu_count() or 2) as pool:
        list(pool.map(convert, jobs))
    return names, figdir


PREAMBLE_MACROS = ("sagerepo", "sagefile", "playgroundurl", "playground")


def preamble(root):
    style = open(os.path.join(root, "chapters", "00_style.tex")).read()
    out = [l for l in style.split("\n")
           if re.match(r"\\(newtheorem|theoremstyle)", l)]
    for name in PREAMBLE_MACROS:
        m = re.search(r"^\\newcommand\{\\%s\}.*?(?=^\\|^%%|^$|\Z)" % name,
                      style, re.M | re.S)
        if not m:
            raise SystemExit("chapters/00_style.tex no longer defines \\%s" % name)
        out.append(m.group(0).strip())
    return "\n".join(out) + "\n"


BADGE_DEF = re.compile(
    r"\\newcommand\{\\(\w+)\}\{\\tikz\b.*?fill=(\w+)!.*?\(s\)\{([^{}]*)\};\}", re.S)


def take_badges(tex):
    badges = {}
    for m in BADGE_DEF.finditer(tex):
        badges[m.group(1)] = (m.group(3), m.group(2).replace("pqc", ""))
    tex = BADGE_DEF.sub("", tex)
    for name in badges:
        tex = re.sub(r"\\%s\b(\\ )?" % name,
                     lambda m, n=name: "BADGE%sBADGE " % n, tex)
    return tex, badges


CAPTIONED = re.compile(r"\\(begin|end)\{(figure|table|algorithm|subfigure)\}|\\caption\{")


def number_captions(tex, floats, used):
    out, at, stack = [], 0, []
    for m in CAPTIONED.finditer(tex):
        if m.group(1) == "begin":
            stack.append(m.group(2))
        elif m.group(1) == "end":
            stack.pop()
        elif stack and stack[-1] in floats:
            kind = stack[-1]
            if used[kind] >= len(floats[kind]):
                raise SystemExit("more %s captions than apqc.aux records" % kind)
            num = floats[kind][used[kind]]
            used[kind] += 1
            out.append(tex[at:m.end()])
            out.append("\\textbf{%s %s.} " % (kind.capitalize(), num))
            at = m.end()
    out.append(tex[at:])
    return "".join(out)


def prepare(tex, stem, drawn, labels, floats, used, missing):
    tex, badges = take_badges(tex)
    tex = splice(tex, drawn_spans(tex),
                 lambda i, s: "\\includegraphics{%s}" % drawn[i])
    tex = number_captions(tex, floats, used)
    tex = re.sub(r"\\(begin|end)\{algorithm\}", r"\\\1{figure}", tex)
    tex = re.sub(r"\\chaptermark\{[^{}]*\}", "", tex)
    tex = re.sub(r"\\printbibliography(\[[^\]]*\])?", "", tex)

    def ref(m):
        key = m.group(1)
        if key not in labels:
            missing.append("%s: \\ref{%s}" % (stem, key))
            return "??"
        return "\\hyperref[%s]{%s}" % (key, labels[key])
    tex = re.sub(r"\\ref\{([^{}]+)\}", ref, tex)
    return tex, badges


def highlight_css(build):
    src = os.path.join(build, "hl.md")
    open(src, "w").write("```python\nx = 1  # c\n```\n")
    html = subprocess.run(["pandoc", src, "--standalone", "--metadata=title:x",
                           "--to=html5"],
                          capture_output=True, text=True, check=True).stdout
    rules = re.findall(r"^\s*((?:pre > )?code(?:\.sourceCode| span)[^{]*\{[^}]*\})",
                       html, re.M)
    return "\n".join(rules)


def run_pandoc(root, src, out):
    cmd = ["pandoc", src, "--from=latex", "--to=html5", "--wrap=none",
           "--mathjax",
           "--citeproc", "--bibliography=" + os.path.join(root, "references.bib"),
           "--csl=" + CSL, "--metadata=link-citations:true",
           "--metadata=reference-section-title:References",
           "--output=" + out]
    run = subprocess.run(cmd, capture_output=True, text=True)
    if run.returncode != 0:
        raise SystemExit("pandoc failed on %s:\n%s" % (src, run.stderr))
    return run.stderr


HEADING = re.compile(r'<h([1-6])((?: [a-z-]+="[^"]*")*)>(.*?)</h\1>', re.S)


def strip_tags(s):
    s = re.sub(r"<[^>]+>", "", s)
    return (s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
             .replace("&quot;", '"').replace("&#39;", "'"))


def svg_size(path):
    head = open(path).read(2000)
    w = re.search(r'width="([\d.]+)(pt)?"', head)
    h = re.search(r'height="([\d.]+)(pt)?"', head)
    return float(w.group(1)), float(h.group(1))


PX_PER_PT = 768 / 468


def finish(html, chapter, where, badges, figdir_url, sizes):
    secs = iter(chapter["sections"])
    subs = iter(chapter["subsections"])
    sections, counted = [], {"2": 0, "3": 0}

    def heading(m):
        level, attrs, inner = m.group(1), m.group(2), m.group(3)
        hid = re.search(r'id="([^"]*)"', attrs)
        hid = hid.group(1) if hid else ""
        cls = re.search(r' class="[^"]*"', attrs)
        cls = cls.group(0) if cls else ""
        if level == "1":
            if strip_tags(inner).strip() == "References":
                sections.append(dict(id=hid, title="References", num="", level=2))
                return '<h2 id="%s" class="unnumbered">%s</h2>' % (hid, inner)
            return ('<h1 id="%s"><span class="secnum">%s %s</span>%s</h1>'
                    % (hid, "Appendix" if chapter["num"].isalpha() else "Chapter",
                       chapter["num"], inner))
        num = ""
        if level in counted and "unnumbered" not in cls:
            try:
                num = next(secs if level == "2" else subs)
            except StopIteration:
                raise SystemExit("%s has more numbered headings than apqc.toc"
                                 % chapter["stem"])
            counted[level] += 1
        if level == "2":
            sections.append(dict(id=hid, title=strip_tags(inner).strip(), num=num,
                                 level=2))
        elif level == "3":
            sections.append(dict(id=hid, title=strip_tags(inner).strip(), num=num,
                                 level=3))
        lead = '<span class="secnum">%s</span>' % num if num else ""
        anchor = '<a class="anchor" href="#%s" aria-label="Link to this section">#</a>' % hid
        return '<h%s id="%s"%s>%s%s%s</h%s>' % (level, hid, cls, lead, inner, anchor, level)

    html = HEADING.sub(heading, html)
    if counted["2"] != len(chapter["sections"]) or counted["3"] != len(chapter["subsections"]):
        raise SystemExit("%s: %d sections and %d subsections on the page, %d and %d "
                         "in apqc.toc" % (chapter["stem"], counted["2"], counted["3"],
                                          len(chapter["sections"]),
                                          len(chapter["subsections"])))

    def link(m):
        key = m.group(1)
        page = where.get(key)
        if page is None or page == chapter["page"]:
            return m.group(0)
        if key.startswith("ch:") or key.startswith("app:"):
            return 'href="%s"' % page
        return 'href="%s#%s"' % (page, key)
    html = re.sub(r'href="#([^"]+)"', link, html)

    html = re.sub(r"<strong>(Definition|Example|Theorem|Proposition|Lemma) 1\.(\d+)</strong>",
                  lambda m: "<strong>%s %s.%s</strong>" % (m.group(1), chapter["num"], m.group(2)),
                  html)
    for name, (text, colour) in badges.items():
        html = html.replace("BADGE%sBADGE " % name,
                            '<span class="badge badge-%s">%s</span> ' % (colour, text))
        html = html.replace("BADGE%sBADGE" % name,
                            '<span class="badge badge-%s">%s</span>' % (colour, text))
    def img(m):
        w, h = sizes[m.group(1)]
        return ('<img src="%s/%s" width="%d" height="%d" loading="lazy"'
                % (figdir_url, m.group(1), round(w * PX_PER_PT), round(h * PX_PER_PT)))
    html = re.sub(r'<img src="(book-[^"]+\.svg)"', img, html)
    html = re.sub(r'(<img [^>]*?)alt="[^"]*"', r'\1alt=""', html)
    return html, sections


def label_pages(sources, chapters):
    where = {}
    for c in chapters:
        for key in re.findall(r"\\label\{([^{}]+)\}", sources[c["stem"]]):
            where[key] = c["page"]
    return where


def search_index(html, chapter):
    out, parts = [], re.split(r'(<h[23] id="[^"]*")', html)
    cur, title = "", chapter["title"]
    buf = parts[0]
    records = []
    for i in range(1, len(parts), 2):
        records.append((cur, title, buf))
        cur = re.search(r'id="([^"]*)"', parts[i]).group(1)
        rest = parts[i + 1]
        h = re.match(r"[^>]*>(.*?)</h[23]>", rest, re.S)
        title = re.sub(r"\s+", " ", strip_tags(h.group(1)).replace("#", "")).strip() if h else ""
        buf = rest
    records.append((cur, title, buf))
    for anchor, t, body in records:
        if t == "References":
            continue
        text = re.sub(r"<pre.*?</pre>", " ", body, flags=re.S)
        text = re.sub(r"\s+", " ", strip_tags(text)).strip()
        out.append(dict(u=chapter["page"] + ("#" + anchor if anchor else ""),
                        c="%s %s" % (chapter["num"], chapter["title"]),
                        t=t, x=text))
    return out


def build(root, dest, build, env, base, css, listings):
    stems = book_order(root)
    items, chapters = parse_toc(root, stems)
    labels, floats = parse_aux(root)
    for c in chapters:
        c["page"] = slug(c["stem"]) + ".html"
    sources = {s: strip_comments(open(os.path.join(root, "chapters", s + ".tex")).read())
               for s in stems}
    where = label_pages(sources, chapters)

    work = os.path.join(build, "book")
    os.makedirs(work, exist_ok=True)
    drawn, figdir = render_drawn(root, work, chapters, sources)
    figout = os.path.join(dest, "book-figures")
    os.makedirs(figout, exist_ok=True)
    sizes = {}
    for c in chapters:
        for name in drawn[c["stem"]]:
            shutil.copyfile(os.path.join(figdir, name), os.path.join(figout, name))
            sizes[name] = svg_size(os.path.join(figdir, name))

    pre = preamble(root)
    used = {k: 0 for k in floats}
    missing = []
    prepared = {}
    for c in chapters:
        tex, badges = prepare(sources[c["stem"]], c["stem"], drawn[c["stem"]],
                              labels, floats, used, missing)
        src = os.path.join(work, c["stem"] + ".tex")
        open(src, "w").write(pre + tex)
        prepared[c["stem"]] = (src, badges)
    for kind in floats:
        if used[kind] != len(floats[kind]):
            raise SystemExit("%d %s captions in the chapters, %d in apqc.aux"
                             % (used[kind], kind, len(floats[kind])))
    if missing:
        raise SystemExit("unresolved references:\n  " + "\n  ".join(missing))

    def convert(c):
        src, _ = prepared[c["stem"]]
        out = src[:-4] + ".html"
        return c["stem"], out, run_pandoc(root, src, out)

    with ThreadPoolExecutor(max_workers=os.cpu_count() or 2) as pool:
        converted = list(pool.map(convert, chapters))
    warnings = {}
    for stem, out, err in converted:
        if err.strip():
            warnings[stem] = err.strip()

    playground = {c["stem"] for c in listings}
    hl = highlight_css(work)
    tpl = env.get_template("book.html")
    index = []
    for c in chapters:
        out = os.path.join(work, c["stem"] + ".html")
        html, c["toc"] = finish(open(out).read(), c, where, prepared[c["stem"]][1],
                                "book-figures", sizes)
        c["html"] = html
        index.extend(search_index(html, c))

    for i, c in enumerate(chapters):
        prev = chapters[i - 1] if i else None
        nxt = chapters[i + 1] if i + 1 < len(chapters) else None
        open(os.path.join(dest, c["page"]), "w").write(tpl.render(
            base, title="%s %s — Applied PQC" % (c["num"], c["title"]),
            css=css + "\n" + hl, main_class="book", here="book",
            items=items, chapter=c, prev=prev, next=nxt,
            playground=("playground-%s.html" % c["stem"]) if c["stem"] in playground else None,
            source="%s/AppliedPQC/blob/main/chapters/%s.tex" % (base["gh"], c["stem"]),
            comments_repo=COMMENTS_REPO, comments_label=COMMENTS_LABEL,
            description="%s %s, from Applied Post-Quantum Cryptography, free to "
                        "read online." % ("Appendix" if c["num"].isalpha() else
                                          "Chapter", c["num"]) + " " + c["title"] + ".",
            page=c["page"], og_type="article", og_title=c["title"], jsonld=None))

    open(os.path.join(dest, "book.html"), "w").write(tpl.render(
        base, title="Read the book online — Applied PQC",
        css=css + "\n" + hl, main_class="book", here="book",
        items=items, chapter=None, prev=None, next=chapters[0],
        playground=None, source=None,
        comments_repo=COMMENTS_REPO, comments_label=COMMENTS_LABEL,
        description="Applied Post-Quantum Cryptography, free to read online: "
                    "every chapter, figure and algorithm of the book.",
        page="book.html", og_type="book", og_title="Applied Post-Quantum Cryptography",
        jsonld=None))

    open(os.path.join(dest, "book-search.json"), "w").write(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")))
    return chapters, warnings

import base64
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
CSL = os.path.join(HERE, "book.csl")

DRAWN = ("tikzpicture", "protocol")
VERBATIM = ("lstlisting", "verbatim")

MATHJAX = ("https://registry.npmjs.org/mathjax/-/mathjax-3.2.2.tgz",
           "sha512-Bt+SSVU8eBG27zChVewOicYs7Xsdt40qm4+UpHyX7k0/O9NliPc+x77k1/FEsPsjKPZGJvtRZM1vO+geW0OhGw==")
MATHJAX_FILES = ("tex-chtml.js", "input/tex/extensions/", "output/chtml/", "ui/", "a11y/", "sre/")

COMMENTS_REPO = "AppliedPQC/AppliedPQC"
COMMENTS_LABEL = "book-comment"

EDITIONS = {
    "en": dict(code="en", lang="en", prefix="", name="English",
               title="Applied Post-Quantum Cryptography",
               figure="Figure", table="Table", algorithm="Algorithm", caption="%s %s.",
               chapter="Chapter %s", appendix="Appendix %s", part="Part %s", colon=": ",
               input="Input:", output="Output:", references="References",
               anchor="Link to this section", theorems={}, playground=None,
               contents="Contents", search="Search the book…", nothing="Nothing found.",
               pdf="PDF", run="Run this chapter's code", source="LaTeX source",
               comments="Comments", start="Start reading", download="Download the PDF",
               previous="Previous", next="Next",
               page_title="%s — Applied PQC", home_title="Read the book online — Applied PQC",
               description="%s, from Applied Post-Quantum Cryptography, free to read "
                           "online. %s.",
               home_description="Applied Post-Quantum Cryptography, free to read online: "
                                "every chapter, figure and algorithm of the book."),
    "zh": dict(code="zh", lang="zh-Hans", prefix="zh-", name="中文",
               title="应用后量子密码学",
               figure="图", table="表", algorithm="算法", caption="%s %s",
               chapter="第 %s 章", appendix="附录 %s", part="第 %s 部分", colon="：",
               input="输入：", output="输出：", references="参考文献",
               anchor="链接到本节",
               theorems={"Definition": "定义", "Example": "例", "Theorem": "定理",
                         "Proposition": "命题", "Lemma": "引理", "Remark": "注"},
               playground="\\newcommand{\\playground}[1]{\\smallskip\\noindent\\emph{在浏览器中运行：}"
                          "#1。参见 \\href{\\playgroundurl}{appliedpqc.io/playground.html}，无需安装。}",
               contents="目录", search="搜索全书…", nothing="没有找到结果。",
               pdf="PDF（英文）", run="运行本章代码", source="LaTeX 源文件",
               comments="评论", start="开始阅读", download="下载 PDF（英文）",
               previous="上一章", next="下一章",
               stale="本章英文原文在翻译之后有过修改，最新内容请以英文版为准。",
               page_title="%s — Applied PQC", home_title="在线阅读《应用后量子密码学》— Applied PQC",
               description="%s，选自《应用后量子密码学》，可免费在线阅读。%s。",
               home_description="《应用后量子密码学》中文版，免费在线阅读：全书的每一章、"
                                "每一幅图和每一个算法。"),
}


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


def preamble(root, ed):
    style = open(os.path.join(root, "chapters", "00_style.tex")).read()
    out = [l for l in style.split("\n")
           if re.match(r"\\(newtheorem|theoremstyle)", l)]
    for en, name in ed["theorems"].items():
        out = [l.replace("{%s}" % en, "{%s}" % name) for l in out]
    for name in PREAMBLE_MACROS:
        m = re.search(r"^\\newcommand\{\\%s\}.*?(?=^\\|^%%|^$|\Z)" % name,
                      style, re.M | re.S)
        if not m:
            raise SystemExit("chapters/00_style.tex no longer defines \\%s" % name)
        out.append(ed["playground"] if name == "playground" and ed["playground"]
                   else m.group(0).strip())
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


def number_captions(tex, floats, used, ed):
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
            out.append("\\textbf{%s} " % (ed["caption"] % (ed[kind], num)))
            at = m.end()
    out.append(tex[at:])
    return "".join(out)


ALG_STATEMENT = re.compile(r"\\(State|Statex|Require|Ensure|If|ElsIf|Else|EndIf|For|ForAll|"
                           r"EndFor|While|EndWhile|Loop|EndLoop|Repeat|Until)(?![A-Za-z])")
ALG_OPEN = {"If": ("if", "then"), "ElsIf": ("else if", "then"), "For": ("for", "do"),
            "ForAll": ("for all", "do"), "While": ("while", "do"), "Until": ("until", "")}
ALG_WORD = {"Else": "else", "EndIf": "end if", "EndFor": "end for", "EndWhile": "end while",
            "Loop": "loop", "EndLoop": "end loop", "Repeat": "repeat"}


def brace_arg(s, i):
    while i < len(s) and s[i].isspace():
        i += 1
    if i >= len(s) or s[i] != "{":
        return None, i
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{" and s[j - 1] != "\\":
            depth += 1
        elif s[j] == "}" and s[j - 1] != "\\":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
    raise SystemExit("unbalanced braces in an algorithm")


def top_level(pattern, s):
    depth, at, out = 0, 0, []
    for m in pattern.finditer(s):
        for ch_i in range(at, m.start()):
            if s[ch_i] == "{" and s[ch_i - 1] != "\\":
                depth += 1
            elif s[ch_i] == "}" and s[ch_i - 1] != "\\":
                depth -= 1
        at = m.start()
        if depth == 0:
            out.append(m)
    return out


def algorithmic(body, numbered, ed):
    body = re.sub(r"\\Return(?![A-Za-z])", r"\\textbf{return}", body)
    marks = top_level(ALG_STATEMENT, body)
    lines, indent, n = [], 0, 0
    for k, m in enumerate(marks):
        kind = m.group(1)
        end = marks[k + 1].start() if k + 1 < len(marks) else len(body)
        arg, at = (brace_arg(body, m.end()) if kind in ALG_OPEN else (None, m.end()))
        rest = re.sub(r"\\hfill(?![A-Za-z])", "", body[at:end]).strip()
        comment = ""
        c = top_level(re.compile(r"\\Comment(?![A-Za-z])"), rest)
        if c:
            comment, after = brace_arg(rest, c[0].end())
            rest = (rest[:c[0].start()] + rest[after:]).strip()
        if kind in ("ElsIf", "Else", "EndIf", "EndFor", "EndWhile", "EndLoop", "Until"):
            indent = max(indent - 1, 0)
        if kind in ALG_OPEN:
            word, tail = ALG_OPEN[kind]
            text = "\\textbf{%s} %s %s %s" % (word, arg or "", "\\textbf{%s}" % tail if tail else "", rest)
        elif kind in ALG_WORD:
            text = "\\textbf{%s} %s" % (ALG_WORD[kind], rest)
        elif kind == "Require":
            text = "\\textbf{%s} %s" % (ed["input"], rest)
        elif kind == "Ensure":
            text = "\\textbf{%s} %s" % (ed["output"], rest)
        else:
            text = rest
        num = 0
        if numbered and kind not in ("Statex", "Require", "Ensure"):
            n += 1
            num = n
        lines.append("XALGLx%dx%dX %s%s" % (num, indent, text.strip(),
                                             " XALGCX " + comment.strip() if comment else ""))
        if kind in ("If", "ElsIf", "Else", "For", "ForAll", "While", "Loop", "Repeat"):
            indent += 1
    return "\n\nXALGBEGINX\n\n" + "\n\n".join(lines) + "\n\nXALGENDX\n\n"


def algorithmic_blocks(tex, ed):
    def one(m):
        return algorithmic(m.group(2), m.group(1) is not None and m.group(1) != "[0]", ed)
    return re.sub(r"\\begin\{algorithmic\}(\[\d+\])?(.*?)\\end\{algorithmic\}", one, tex,
                  flags=re.S)


ALG_HTML = re.compile(r"<p>XALGBEGINX</p>(.*?)<p>XALGENDX</p>", re.S)
ALG_LINE = re.compile(r"<p>XALGLx(\d+)x(\d+)X\s*(.*?)</p>", re.S)


def algorithm_html(html):
    def block(m):
        out = []
        for n, indent, text in ALG_LINE.findall(m.group(1)):
            text, _, comment = text.partition("XALGCX")
            out.append('<div class="alg-line" style="--i:%s"><span class="alg-no">%s</span>'
                       '<span class="alg-text">%s</span>%s</div>'
                       % (indent, n + ":" if n != "0" else "", text.strip(),
                          '<span class="alg-comment">\u25b7 %s</span>' % comment.strip()
                          if comment else ""))
        return '<div class="algorithmic">%s</div>' % "".join(out)
    return ALG_HTML.sub(block, html)


MATH = re.compile(r"(?<!\\)\$\$.*?(?<!\\)\$\$|(?<!\\)\$.*?(?<!\\)\$|\\\(.*?\\\)|\\\[.*?\\\]|"
                  r"\\begin\{(equation|align|gather|multline)(\*?)\}.*?\\end\{\1\2\}", re.S)


def small_caps(word):
    out = []
    for run in re.findall(r"[a-z]+|[^a-z]+", word):
        out.append("{\\small\\text{%s}}" % run.upper() if run.islower() else "\\text{%s}" % run)
    return "".join(out)


def math_aware(tex):
    def text(s):
        return re.sub(r"\\qquad(?![A-Za-z])\s*", "\u2003\u2003",
                      re.sub(r"\\quad(?![A-Za-z])\s*", "\u2003", s))

    def math(s):
        return re.sub(r"\\textsc\{([^{}]*)\}", lambda m: small_caps(m.group(1)), s)

    out, at = [], 0
    for a, b in verbatim_spans(tex) + [(len(tex), len(tex))]:
        chunk, pos = tex[at:a], 0
        for m in MATH.finditer(chunk):
            out.append(text(chunk[pos:m.start()]))
            out.append(math(m.group(0)))
            pos = m.end()
        out.append(text(chunk[pos:]))
        out.append(tex[a:b])
        at = b
    return "".join(out)


def prepare(tex, stem, drawn, labels, floats, used, missing, ed):
    tex, badges = take_badges(tex)
    tex = algorithmic_blocks(tex, ed)
    tex = splice(tex, drawn_spans(tex),
                 lambda i, s: "\\includegraphics{%s}" % drawn[i])
    tex = math_aware(tex)
    tex = number_captions(tex, floats, used, ed)
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


def run_pandoc(root, src, out, ed):
    cmd = ["pandoc", src, "--from=latex", "--to=html5", "--wrap=none",
           "--mathjax",
           "--citeproc", "--bibliography=" + os.path.join(root, "references.bib"),
           "--csl=" + CSL, "--metadata=link-citations:true",
           "--metadata=reference-section-title:" + ed["references"],
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


def finish(html, chapter, where, badges, figdir_url, sizes, ed):
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
            if strip_tags(inner).strip() == ed["references"]:
                sections.append(dict(id=hid, title=ed["references"], num="", level=2))
                return '<h2 id="%s" class="unnumbered">%s</h2>' % (hid, inner)
            return ('<h1 id="%s"><span class="secnum">%s</span>%s</h1>'
                    % (hid, numbered(chapter, ed), inner))
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
        anchor = '<a class="anchor" href="#%s" aria-label="%s">#</a>' % (hid, ed["anchor"])
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

    html = algorithm_html(html)
    names = list(ed["theorems"].values()) or ["Definition", "Example", "Theorem",
                                              "Proposition", "Lemma"]
    html = re.sub(r"<strong>(%s) 1\.(\d+)</strong>" % "|".join(names),
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


def vendor_mathjax(dest):
    url, integrity = MATHJAX
    try:
        data = urllib.request.urlopen(url, timeout=60).read()
    except Exception as exc:
        raise SystemExit("could not fetch MathJax from %s\n%s" % (url, exc))
    algo, want = integrity.split("-", 1)
    if base64.b64encode(hashlib.new(algo, data).digest()).decode() != want:
        raise SystemExit("MathJax from %s does not match its pinned %s hash" % (url, algo))
    out = os.path.join(dest, "mathjax")
    n = 0
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for m in tar.getmembers():
            if not m.isfile() or not m.name.startswith("package/es5/"):
                continue
            rel = m.name[len("package/es5/"):]
            if not rel.startswith(MATHJAX_FILES) or ".." in rel.split("/"):
                continue
            path = os.path.join(out, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "wb").write(tar.extractfile(m).read())
            n += 1
    if not os.path.exists(os.path.join(out, "tex-chtml.js")):
        raise SystemExit("the MathJax package has no es5/tex-chtml.js")
    return n


def numbered(chapter, ed):
    return (ed["appendix"] if chapter["num"].isalpha() else ed["chapter"]) % chapter["num"]


def blob_sha(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def translation(root, items, chapters, sources):
    zdir = os.path.join(root, "chapters", "zh")
    if not os.path.isdir(zdir):
        return None
    absent = [c["stem"] for c in chapters
              if not os.path.exists(os.path.join(zdir, c["stem"] + ".tex"))]
    if absent:
        raise SystemExit("chapters/zh has no translation of %s" % ", ".join(absent))
    parts = re.findall(r"^\\(part|subpart)\*?\{(.*)\}\s*$",
                       strip_comments(open(os.path.join(zdir, "parts.tex")).read()), re.M)
    if [k for k, _ in parts] != [it["kind"] for it in items if it["kind"] != "chapter"]:
        raise SystemExit("chapters/zh/parts.tex does not list apqc.tex's parts and "
                         "subparts in order")
    zsources, zchapters = {}, {}
    for c in chapters:
        raw = open(os.path.join(zdir, c["stem"] + ".tex"), "rb").read()
        tex = strip_comments(raw.decode())
        if [tex[a:b] for a, b in drawn_spans(tex)] != \
                [sources[c["stem"]][a:b] for a, b in drawn_spans(sources[c["stem"]])]:
            raise SystemExit("chapters/zh/%s.tex does not carry the English drawings "
                             "unchanged" % c["stem"])
        label = re.compile(r"\\label\{([^{}]+)\}")
        if label.findall(tex) != label.findall(sources[c["stem"]]):
            raise SystemExit("chapters/zh/%s.tex does not carry the English labels in "
                             "order" % c["stem"])
        m = re.search(r"\\chapter\*?(\[[^\]]*\])?", tex)
        if not m:
            raise SystemExit("chapters/zh/%s.tex has no \\chapter" % c["stem"])
        title, _ = brace_arg(tex, m.end())
        stamp = re.search(rb"^% source: ([0-9a-f]{40})", raw, re.M)
        english = open(os.path.join(root, "chapters", c["stem"] + ".tex"), "rb").read()
        zsources[c["stem"]] = tex
        zchapters[c["stem"]] = dict(
            c, title=tex_text(title), page="zh-" + c["page"],
            stale=not stamp or stamp.group(1).decode() != blob_sha(english))
    heads = iter(parts)
    zitems = [zchapters[it["stem"]] if it["kind"] == "chapter"
              else dict(it, title=tex_text(next(heads)[1])) for it in items]
    return zitems, [zchapters[c["stem"]] for c in chapters], zsources


def build(root, dest, build, env, base, css, listings):
    stems = book_order(root)
    items, chapters = parse_toc(root, stems)
    labels, floats = parse_aux(root)
    for c in chapters:
        c["page"] = slug(c["stem"]) + ".html"
        c["title_en"] = c["title"]
        c["stale"] = False
    sources = {s: strip_comments(open(os.path.join(root, "chapters", s + ".tex")).read())
               for s in stems}

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

    playground = {c["stem"] for c in listings}
    hl = highlight_css(work)
    tpl = env.get_template("book.html")
    editions = [(EDITIONS["en"], items, chapters, sources)]
    zh = translation(root, items, chapters, sources)
    if zh:
        editions.append((EDITIONS["zh"],) + zh)
    other = {}
    for ed, _, eds_chapters, _ in editions:
        for c in eds_chapters:
            other.setdefault(c["stem"], []).append(dict(page=c["page"], lang=ed["lang"],
                                                        name=ed["name"]))
    homes = [dict(page=ed["prefix"] + "book.html", lang=ed["lang"], name=ed["name"])
             for ed, _, _, _ in editions]
    warnings = {}

    def publish(ed, items, chapters, sources):
        where = {k: ed["prefix"] + v for k, v in label_pages(sources, chapters).items()}
        pre = preamble(root, ed)
        used = {k: 0 for k in floats}
        missing = []
        prepared = {}
        for c in chapters:
            tex, badges = prepare(sources[c["stem"]], c["stem"], drawn[c["stem"]],
                                  labels, floats, used, missing, ed)
            src = os.path.join(work, ed["prefix"] + c["stem"] + ".tex")
            open(src, "w").write(pre + tex)
            prepared[c["stem"]] = (src, badges)
        for kind in floats:
            if used[kind] != len(floats[kind]):
                raise SystemExit("%s: %d %s captions in the chapters, %d in apqc.aux"
                                 % (ed["name"], used[kind], kind, len(floats[kind])))
        if missing:
            raise SystemExit("unresolved references:\n  " + "\n  ".join(missing))

        def convert(c):
            src, _ = prepared[c["stem"]]
            out = src[:-4] + ".html"
            return ed["prefix"] + c["stem"], out, run_pandoc(root, src, out, ed)

        with ThreadPoolExecutor(max_workers=os.cpu_count() or 2) as pool:
            converted = list(pool.map(convert, chapters))
        for stem, out, err in converted:
            if err.strip():
                warnings[stem] = err.strip()

        index = []
        for c, (_, out, _) in zip(chapters, converted):
            html, c["toc"] = finish(open(out).read(), c, where, prepared[c["stem"]][1],
                                    "book-figures", sizes, ed)
            c["html"] = html
            index.extend(search_index(html, c))

        common = dict(css=css + "\n" + hl, main_class="book", here="book", items=items,
                      ed=ed, lang=ed["lang"], home=ed["prefix"] + "book.html",
                      search_index=ed["prefix"] + "book-search.json",
                      comments_repo=COMMENTS_REPO, comments_label=COMMENTS_LABEL)
        for i, c in enumerate(chapters):
            prev = chapters[i - 1] if i else None
            nxt = chapters[i + 1] if i + 1 < len(chapters) else None
            source = "chapters/%s%s.tex" % ("zh/" if ed["prefix"] else "", c["stem"])
            open(os.path.join(dest, c["page"]), "w").write(tpl.render(
                base, **common,
                title=ed["page_title"] % ("%s %s" % (c["num"], c["title"])),
                chapter=c, prev=prev, next=nxt,
                playground=("playground-%s.html" % c["stem"]) if c["stem"] in playground
                else None,
                source="%s/AppliedPQC/blob/main/%s" % (base["gh"], source),
                english=[o for o in other[c["stem"]] if o["lang"] == "en"][0]["page"],
                alternates=other[c["stem"]] if len(other[c["stem"]]) > 1 else [],
                description=ed["description"] % (numbered(c, ed), c["title"]),
                page=c["page"], og_type="article", og_title=c["title"], jsonld=None))

        open(os.path.join(dest, ed["prefix"] + "book.html"), "w").write(tpl.render(
            base, **common,
            title=ed["home_title"], chapter=None, prev=None, next=chapters[0],
            playground=None, source=None, english="book.html",
            alternates=homes if len(homes) > 1 else [],
            description=ed["home_description"],
            page=ed["prefix"] + "book.html", og_type="book", og_title=ed["title"],
            jsonld=None))
        open(os.path.join(dest, ed["prefix"] + "book-search.json"), "w").write(
            json.dumps(index, ensure_ascii=False, separators=(",", ":")))

    for ed, eds_items, eds_chapters, eds_sources in editions:
        publish(ed, eds_items, eds_chapters, eds_sources)
    vendor_mathjax(dest)
    return chapters, warnings

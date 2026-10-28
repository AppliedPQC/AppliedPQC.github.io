"""The site's languages, and the Chinese text of every string the templates show.

Templates keep their English inline and wrap it as ``{{ _("...") }}``; the
Chinese comes from ``i18n/zh.json``, keyed by the English with its whitespace
collapsed. A string with no entry is collected rather than shown in English,
and the build fails listing every one, so a page can never go out half
translated.
"""

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

LANGS = (
    dict(code="en", lang="en", prefix="", name="English"),
    dict(code="zh", lang="zh-Hans", prefix="zh-", name="中文"),
)
CATALOG = json.load(open(os.path.join(HERE, "i18n", "zh.json")))
missing = set()


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def gettext(code):
    if code == "en":
        return lambda s: s

    def _(s):
        key = norm(s)
        if key not in CATALOG:
            missing.add(key)
            return s
        return CATALOG[key]
    return _


def other(code):
    return [l for l in LANGS if l["code"] != code][0]


def chrome(code, page, counterpart=True):
    """Template variables that make a page part of one language of the site.

    ``page`` is the English file name; the Chinese page is the same name with
    the ``zh-`` prefix. The home page is the exception on the English side,
    whose canonical address is the site root.
    """
    here = [l for l in LANGS if l["code"] == code][0]
    there = other(code)
    names = {l["code"]: l["prefix"] + page for l in LANGS}
    canonical = dict(names, en="" if page == "index.html" else names["en"])
    alt = names[there["code"]] if counterpart else there["prefix"] + "index.html"
    return dict(lang=here["lang"], p=here["prefix"], _=gettext(code),
                page=canonical[code], alt=alt, alt_lang=there["lang"],
                alt_name=there["name"],
                alternates=[dict(lang=l["lang"], page=canonical[l["code"]])
                            for l in LANGS] if counterpart else [])


def check():
    if missing:
        raise SystemExit("strings with no Chinese in pages/i18n/zh.json:\n  "
                         + "\n  ".join(sorted(missing)))

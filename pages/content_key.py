#!/usr/bin/env python3
"""Compute a key covering every repository the site build reads.

The book is checked out by the workflow, so its commit is known locally. Blog
posts listed in ``blog/sources.json`` are a different matter: they are fetched
from other AppliedPQC repositories at build time and never copied into this
one, so the book's commit alone does not say whether the published site is
current. Keying the freshness check on the book alone means an edit to a
sourced post never triggers a rebuild -- the site simply stays stale.

Prints a single sha256 digest over the book commit and the head commit of every
repository named in the sources file. A source that cannot be read yields a
value that matches no previous key, so the build runs rather than risk skipping
a change it could not see.
"""

import hashlib
import json
import os
import sys
import urllib.request

API = "https://api.github.com/repos/AppliedPQC/%s/commits/main"


def head(repo):
    """Return the head commit sha of ``repo``'s main branch."""
    request = urllib.request.Request(
        API % repo, headers={"Accept": "application/vnd.github+json"}
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)["sha"]


def repos(sources_path):
    """Return the distinct repositories the sources file draws posts from."""
    try:
        with open(sources_path) as handle:
            sources = json.load(handle)
    except FileNotFoundError:
        return []
    return sorted({s["repo"] for s in sources if s.get("repo")})


def main(book_sha, sources_path):
    parts = ["book:%s" % book_sha]
    for repo in repos(sources_path):
        try:
            parts.append("%s:%s" % (repo, head(repo)))
        except Exception as exc:  # network, rate limit, renamed repo
            print("could not read %s: %s" % (repo, exc), file=sys.stderr)
            parts.append("%s:unknown-%s" % (repo, os.environ.get("GITHUB_RUN_ID", "0")))
    print(hashlib.sha256("\n".join(parts).encode()).hexdigest())


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: content_key.py <book-sha> [sources.json]")
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "blog/sources.json")

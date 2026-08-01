# appliedpqc.io

The website for [Applied PQC](https://appliedpqc.io/), served by GitHub Pages
from this repository.

`pages/` holds the site: the Jinja templates, the stylesheets, the playground
prose, and the two scripts that build and check it.

`blog/` holds the posts, which are this site's own content rather than the
book's.

What it renders from elsewhere comes from
[AppliedPQC/AppliedPQC](https://github.com/AppliedPQC/AppliedPQC) — the LaTeX
book, the SageMath implementations, and the listing data generated from the
chapters. That repository is checked out at build time and never copied here, so
there is nothing to drift.
[`build-info.json`](https://appliedpqc.io/build-info.json) names the exact source
commit the live site was built from.

The book repository checks out `pages/` in its own CI and runs the same build
and the same checks on every pull request, so a chapter change that would break
a page is caught in review rather than after publishing.

## How it updates

GitHub cannot notify this repository when the source changes, so the workflow
polls hourly. The poll is cheap: it compares the source commit against the one
in the live `build-info.json` and stops before installing anything if they
match. A build takes a few minutes, so a change to the book appears here within
about an hour.

To publish immediately, run the workflow by hand:

```sh
gh workflow run deploy.yml --repo AppliedPQC/AppliedPQC.github.io
```

Nothing here needs a secret. The source repository is public, so it is checked
out with no token.

## Layout

```text
pages/build_site.py     builds the whole site
pages/check_site.py     asserts the result is what it should be
pages/templates/        Jinja templates; the chrome is defined once
pages/styles/           stylesheets
pages/playground.md     the playground's prose
blog/                   posts, and sources.json for posts held elsewhere
```

Adding a blog post is one file in `blog/` — see [`blog/README.md`](blog/README.md).

Pages is set to build from Actions, so nothing in this repository is served
directly: the deployed artifact is the site.

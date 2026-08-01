# appliedpqc.io

The website for [Applied PQC](https://appliedpqc.io/), served by GitHub Pages
from this repository.

There is no page source here. The site is **built from
[AppliedPQC/AppliedPQC](https://github.com/AppliedPQC/AppliedPQC)** — the book,
the SageMath implementations and the page templates all live there — and
published by `.github/workflows/deploy.yml`.

Keeping the source in one repository and publishing from another means this
repository holds no copy that could drift. What it publishes is recorded in
[`build-info.json`](https://appliedpqc.io/build-info.json), which names the
exact source commit the live site was built from.

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

## What is in this repository

Only the workflow. Pages is set to build from Actions, so nothing in this
repository is served — the deployed artifact is the site, and it carries its
own `.nojekyll`. The page templates and stylesheets live with the book, in
[`.github/pages/`](https://github.com/AppliedPQC/AppliedPQC/tree/main/.github/pages)
of the source repository, because they render data generated from the book's
own LaTeX. Keeping them there means a chapter change and the page that shows it
are one review, and the source repository's CI can check the rendered site
before a change is merged.

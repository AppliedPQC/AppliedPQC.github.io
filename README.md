# appliedpqc.io

The organization site for [Applied PQC](https://appliedpqc.io/), served by
GitHub Pages from this repository's `main` branch.

Because this is the organization site, the custom domain cascades to the
organization's project sites, which are served under it by path:

| URL | Repository |
| --- | --- |
| <https://appliedpqc.io/> | this repository |
| <https://appliedpqc.io/AppliedPQC/> | [AppliedPQC/AppliedPQC](https://github.com/AppliedPQC/AppliedPQC) — the book |
| <https://appliedpqc.io/AppliedPQC/apqc.pdf> | the compiled book PDF |

The page is a single self-contained `index.html`: no build step, no
dependencies, nothing to break between a commit and a deploy. Links are
checked on every change and weekly by `.github/workflows/link-check.yml`.

# Blog sources

Posts come from two places.

**Written here.** A Markdown file in this directory with a metadata block:

```markdown
---
title: What the post is called
date: 2026-08-01
summary: One or two sentences for the index.
---

The body, in Markdown.
```

**Sourced from another repository.** An entry in `sources.json`. The post is
fetched at build time and rendered; it is never copied into this repository, so
the canonical document stays the single source and the two cannot diverge. The
title is read from the document's own top-level heading, and the rendered page
carries a note pointing back to the original.

```json
{
  "slug": "url-slug",
  "date": "2026-08-01",
  "repo": "pqc-research",
  "path": "some-document.md",
  "summary": "One or two sentences for the index."
}
```

`repo` is a repository under `github.com/AppliedPQC`, `path` is the file inside
it. An optional `summary_zh` is the summary on the Chinese index.

**Chinese.** Every post also has a Chinese page, `zh-blog-<slug>.html`. For a
sourced post its text is `zh/<name>` beside the original in the other
repository; for a post written here it is `blog/zh/<name>.md`. Until that file
exists, the Chinese page shows the English with a note saying so. Both kinds appear together on the blog index and the landing page, newest
first.

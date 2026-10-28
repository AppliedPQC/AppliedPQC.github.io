
## {{ _("Every listing in the book") }}

{{ _("All %d code listings from the chapters, runnable the same way.
Each cell replays its chapter's earlier listings first, so any snippet can be
tried on its own.")|format(n_listings) }}

<ul class="grid" data-filter="all">
{%- for c in chapters %}
<li class="card" data-cat="chapter" data-text="{{ c.title|lower }}">
{{ art(c.art, loop.index0) }}
<div class="card-body">
<h3><a class="stretch" href="{{ p }}playground-{{ c.stem }}.html">{{ c.title }}</a></h3>
<p class="meta"><span class="tag">{{ _("1 listing") if c.listings|length == 1 else _("%d listings")|format(c.listings|length) }}</span><span>{{ _("runs in your browser") }}</span></p>
</div>
</li>
{%- endfor %}
</ul>

<p class="empty" hidden>{{ _("Nothing matches that.") }}</p>

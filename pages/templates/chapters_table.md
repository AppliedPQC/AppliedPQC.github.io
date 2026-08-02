
## Every listing in the book

All {{ n_listings }} code listings from the chapters, runnable the same way.
Each cell replays its chapter's earlier listings first, so any snippet can be
tried on its own.

<ul class="grid" data-filter="all">
{%- for c in chapters %}
<li class="card" data-cat="chapter" data-text="{{ c.title|lower }}">
{{ art(c.art, loop.index0) }}
<div class="card-body">
<h3><a class="stretch" href="playground-{{ c.stem }}.html">{{ c.title }}</a></h3>
<p class="meta"><span class="tag">{{ c.listings|length }} listing{{ '' if c.listings|length == 1 else 's' }}</span><span>runs in your browser</span></p>
</div>
</li>
{%- endfor %}
</ul>

<p class="empty" hidden>Nothing matches that.</p>

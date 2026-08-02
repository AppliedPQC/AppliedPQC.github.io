# Blog

Notes and research from the Applied PQC project.

{% if posts -%}
<ul class="grid" data-filter="all">
{%- for p in posts %}
<li class="card" data-cat="writing" data-text="{{ p.title|lower }} {{ (p.summary or '')|lower }}">
{{ art('post', loop.index0) }}
<div class="card-body">
<h3><a class="stretch" href="blog-{{ p.slug }}.html">{{ p.title }}</a></h3>
{% if p.summary %}<p>{{ p.summary }}</p>{% endif %}
<p class="meta"><span class="tag">Post</span><span>{{ p.date }}</span></p>
</div>
</li>
{%- endfor %}
</ul>

<p class="empty" hidden>Nothing matches that.</p>
{%- else %}
No posts yet.
{%- endif %}

# {{ _("Blog") }}

{{ _("Notes and research from the Applied PQC project.") }}

{% if posts -%}
<ul class="grid" data-filter="all">
{%- for post in posts %}
<li class="card" data-cat="writing" data-text="{{ post.title|lower }} {{ (post.summary or '')|lower }}">
{{ art('post', loop.index0) }}
<div class="card-body">
<h3><a class="stretch" href="blog-{{ post.slug }}.html">{{ post.title }}</a></h3>
{% if post.summary %}<p>{{ post.summary }}</p>{% endif %}
<p class="meta"><span class="tag">{{ _("Post") }}</span><span>{{ post.date }}</span></p>
</div>
</li>
{%- endfor %}
</ul>

<p class="empty" hidden>{{ _("Nothing matches that.") }}</p>
{%- else %}
{{ _("No posts yet.") }}
{%- endif %}

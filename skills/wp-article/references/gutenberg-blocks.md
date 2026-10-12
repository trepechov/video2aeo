# Gutenberg markup produced by the renderer

The renderer emits serialized core blocks that match WordPress 6.5+ `save()` output, so they open in the block
editor without "This block contains unexpected content". Use these only to understand or debug the output.

```html
<!-- wp:embed {"url":"https://www.youtube.com/watch?v=ID","type":"video","providerNameSlug":"youtube","responsive":true,"className":"wp-embed-aspect-16-9 wp-has-aspect-ratio"} -->
<figure class="wp-block-embed is-type-video is-provider-youtube wp-block-embed-youtube wp-embed-aspect-16-9 wp-has-aspect-ratio"><div class="wp-block-embed__wrapper">
https://www.youtube.com/watch?v=ID
</div><figcaption class="wp-element-caption">…</figcaption></figure>
<!-- /wp:embed -->

<!-- wp:paragraph {"className":"aeo-answer"} -->
<p class="aeo-answer"><strong>Кратък отговор:</strong> …</p>
<!-- /wp:paragraph -->

<!-- wp:heading {"anchor":"chesto-zadavani-vaprosi"} -->
<h2 class="wp-block-heading" id="chesto-zadavani-vaprosi">Често задавани въпроси</h2>
<!-- /wp:heading -->

<!-- wp:list -->
<ul class="wp-block-list"><!-- wp:list-item -->
<li>…</li>
<!-- /wp:list-item --></ul>
<!-- /wp:list -->

<!-- wp:table {"hasFixedLayout":false} -->
<figure class="wp-block-table"><table><thead><tr><th>…</th></tr></thead><tbody><tr><td>…</td></tr></tbody></table></figure>
<!-- /wp:table -->

<!-- wp:details -->
<details class="wp-block-details"><summary>Покажи пълния редактиран транскрипт</summary><!-- wp:paragraph -->
<p>…</p>
<!-- /wp:paragraph --></details>
<!-- /wp:details -->

<!-- wp:html -->
<script type="application/ld+json">{…}</script>
<!-- /wp:html -->
```

## Pasting manually (phase 1)

Posts → Add New → ⋮ (top right) → **Code editor** → paste the whole `article.wp.html` → **Exit code editor** →
set title, slug, category, tags, featured image (the video thumbnail) and SEO fields from `wp-post-fields.json` →
Preview → Save draft. If a block shows a warning, choose "Attempt recovery" and report it so the renderer is fixed.

The Custom HTML block with `<script>` requires a role with `unfiltered_html` (Administrator/Editor on single site).
If Rank Math / Yoast already outputs Article/VideoObject, set `"jsonld_in_content": false` in the brand override and
add the FAQ/Clip data through the SEO plugin instead, so the page never has two competing VideoObjects.

## Suggested theme CSS (once, in Customizer → Additional CSS)

```css
.aeo-answer{border-left:4px solid currentColor;padding:.75rem 1rem;background:rgba(0,0,0,.04);font-size:1.05em}
.aeo-note{font-size:.9em;opacity:.85}
.aeo-section-answer{font-weight:600}
.aeo-disclaimer{font-size:.85em;opacity:.75}
```

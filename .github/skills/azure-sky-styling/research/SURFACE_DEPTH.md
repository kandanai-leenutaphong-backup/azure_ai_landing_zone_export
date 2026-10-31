# Surface Depth Without Clutter

Implementation follow-up: [Surface Depth Recipes](../DEPTH_EFFECTS.md) maps the
six techniques below to isolated CSS modules and verified browser specimens. This
document retains the pre-implementation reasoning and proposed strengths.

Research date: 2026-09-10. Research only; no UI change or material-performance
measurement. Scope is the Azure Sky style gallery, not a consuming application. Clouds and orange
accents remain removed; muted mint remains a secondary accent.

## Recommendation

Test a satin-like blue surface: fine static grain, one consistent lit edge, and a
small blue-tinted contact shadow. Keep layout, spacing and typography unchanged.
The aim is to make a color feel like a material, not to add more containers or
make every section float.

The current stylesheet already provides broad gradients, surface glazing, a blurred
navigation background and a layered material specimen. Increasing gradient strength
or blur everywhere would repeat those cues, not necessarily improve depth.

## Candidate Techniques

All numeric strengths below are proposed starting points, not measurements or
accessibility guarantees. Effects must be compared on the same surface/content.

| Technique | Visual Contribution | Proposed Azure Sky Trial |
| --- | --- | --- |
| Fine static grain | Breaks perfectly uniform digital fills; a tactile surface rather than a new object. | A tiny reusable grayscale noise tile at 1-2% overlay opacity, below text; static, not animated. Avoid visible dots, regular patterns, or full-screen live turbulence. |
| Directional edge light | Suggests thickness and one shared light source without changing geometry. | A 1px inset upper-edge highlight, initially 8-15% white on Cobalt; a much quieter lower edge. Apply to controls and selected framed tools, not every section. |
| Contact plus ambient shadow | A tight shadow anchors a surface; a broader faint shadow implies a little separation. | Start with a 1px-offset/2px-blur blue shadow and a second 6px-offset/16px-blur wash. Keep them faint, with the same light direction. Use only on actual overlays or framed controls. |
| Color-matched shading | Retains blue richness that a gray/black shadow can muddy. | Shade toward deeper blue and reflect toward pale azure; author a small lightness/chroma change before increasing blur or contrast. Mint belongs in occasional reflections, not a broad green wash. |
| Broad restrained sheen | Reads as reflected light within one surface, unlike an extra card or decorative orb. | A single wide off-center white-to-transparent wash at a proposed 2-4% strength, clipped to the surface. No animated spotlight or visible shine stripe. |
| Tonal hierarchy | Adjacent planes feel distinct even with no translucency. | Make the workspace ground slightly quieter than the working surface, and reserve the strongest edge/contrast cue for selection or focus. Preserve readable labels. |

The edge-light and sheen values are design proposals derived from lighting
principles, not settings prescribed by the sources. They need browser comparison.

## Source Findings

1. [Fluent 2: Elevation](https://fluent2.microsoft.design/elevation) describes depth
   as the interplay of light and shadow, with a consistent direction. Its shadow
   system combines a crisp directional/key shadow with a softer ambient shadow.
   This supports a coordinated pair of cues instead of a large generic blur.
2. [Josh W. Comeau: Designing Beautiful Shadows](https://www.joshwcomeau.com/css/designing-shadows/)
   explains consistent light direction, layered shadows, and color-matched shadow
   hues. It also cautions about the rendering cost of many shadow layers and
   animating layered shadows. Its examples do not establish a performance budget
   for this gallery.
3. [CSS-Tricks: Grainy Gradients](https://css-tricks.com/grainy-gradients/)
   demonstrates texture through SVG turbulence, gradient layering, and filtering.
   The Azure Sky recommendation is a much fainter static grain, not the article's
   high-contrast colorful effect. A cached tile is a proposed implementation choice;
   no SVG filter or bitmap was added here.
4. [Microsoft: Acrylic Material](https://learn.microsoft.com/en-us/windows/apps/design/style/acrylic)
   combines translucency, blur, tint and noise to give flat surfaces dimension.
   It warns against stacked acrylic layers, recommends opaque backgrounds for
   ordinary vertical panes, and names GPU/power and legibility costs. This is
   Windows material guidance, not a promise of identical CSS behavior.
5. [MDN: linear-gradient](https://developer.mozilla.org/en-US/docs/Web/CSS/gradient/linear-gradient)
   documents explicit color-space interpolation, including Oklab and Oklch. These
   provide control over gradient transitions; color-space choice alone does not
   create material depth. Retain a supported fallback when adopting new syntax.

## Suggested Comparison

Use one existing Cobalt specimen, same size and text, in three states:

- Current flat/gradient baseline.
- Baseline plus fine grain.
- Baseline plus grain, directional edge light and a restrained contact shadow.

Compare at normal viewing size, not only magnified. Reject treatments that look
speckled, beveled, glossy, cloudy, or less legible. Do not stack every technique at
once. Leave text opacity at 1 and check the composited background contrast, focus
outline, mobile appearance, forced-colors behavior, and reduced-transparency
fallback. Browser and physical-device performance remain unmeasured.

## Acquisition

No ranked web-search provider was configured. These five primary references were
retrieved directly using the repository's robots-aware fetcher. The source list is
[surface-depth-sources.txt](surface-depth-sources.txt). Third-party HTML and text
extracts are held outside the repository under `/tmp/azure-sky-depth-research/pages/`;
the catalogue records source URL, acquisition time and content hash. No source code
or artwork from those pages was incorporated into the application.

After separate acquisition authorization, use installed `webres` and set `LIBRARY_ROOT` to the
Azure Sky library to refresh just the HTML holdings:

```bash
python3 -m webres.cli.fetch_page \
   --urls "$LIBRARY_ROOT/research/surface-depth-sources.txt" \
  --subject azure-sky-surface-depth --out /tmp/azure-sky-depth-sources/pages \
  --catalogue /tmp/azure-sky-depth-sources/catalogue.json
python3 -m webres.cli.catalogue \
  --catalogue /tmp/azure-sky-depth-sources/catalogue.json --verify
```

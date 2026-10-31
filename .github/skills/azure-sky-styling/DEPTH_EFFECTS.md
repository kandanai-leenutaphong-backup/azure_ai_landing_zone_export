# Surface Depth Recipes

Azure Sky's standard blue material combines static grain at 3%, edge light,
layered shadow and blue shading. Sheen and tonal ground remain optional.
Light surfaces use a separate cool-stain finish with 2% grain. Cloud is a shaded
off-white, `#EFF3F8`; pure white remains reserved for highlights and inverse text.
Open http://127.0.0.1:4317/ to see it across the gallery, or
http://127.0.0.1:4317/#depth for the isolated effects. The baseline and combination
use identical content and dimensions. Every isolated specimen names its CSS class
and has a copy button; the combination has toggles, grain opacity, copy, and reset.
No settings persist or affect a consuming application.

## Source Map

| Responsibility | File |
| --- | --- |
| Portable paint, seven numbered effect blocks, accessibility fallbacks | [frontend/depth-effects.css](frontend/depth-effects.css) |
| Blue and light materials applied to existing roles, without changing geometry | [frontend/azure-sky.css](frontend/azure-sky.css) |
| Effect IDs, labels, target surface, default selection, recipe generation | [frontend/depthEffects.ts](frontend/depthEffects.ts) |
| React specimens, toggles, clipboard and visible failure recovery | [frontend/DepthStudy.tsx](frontend/DepthStudy.tsx) |
| Gallery-only layout and responsive geometry | [frontend/depth-study.css](frontend/depth-study.css) |
| Original, seeded texture generation | [scripts/generate-grain.mjs](scripts/generate-grain.mjs) |

The reusable stylesheet has no React, Tailwind, font, theme-root, animation or
JavaScript dependency. It uses explicit `azs-depth-*` classes, not a global reset.
The package export is `@harness/azure-sky-styling/depth.css`.
When `.azure-sky` is present, the same effect blocks supply inherited paint slots
for the theme. Standalone specimens reset their own slots, preserving isolation.

## One Effect Alone

The neutral `.azs-depth-surface` supplies the Cobalt fill, white foreground and
composition slots. Add exactly one effect class for an isolated result:

```html
<link rel="stylesheet" href="./frontend/depth-effects.css">

<div class="azs-depth-surface azs-depth-edge-light" style="padding: 24px">
  Azure Sky
</div>
```

Replace `.azs-depth-edge-light` with any surface class in the table. The examples
below share only the base paint contract; no effect silently enables another.

| ID / Label | Isolated Class | Mechanism / Default |
| --- | --- | --- |
| 01 / Static grain | `.azs-depth-grain` | Repeating 128x128 monochrome PNG on `::before`, at 3% opacity, below content. Tune `--azs-depth-grain-opacity: .03`. |
| 02 / Edge light | `.azs-depth-edge-light` | White 1px inset upper edge at 15%, dark blue 1px lower edge at 18%. Tune `--azs-depth-edge-opacity: .15`. |
| 03 / Layered shadow | `.azs-depth-shadow` | Blue contact shadow: `0 1px 2px` at 16%; blue ambient shadow: `0 6px 16px` at 10%. No positional transform. |
| 04 / Blue shading | `.azs-depth-blue-shading` | `#205A9F` to `#123F91` to `#103678`, 155-degree gradient; Oklab interpolation when supported, ordinary gradient fallback. |
| 05 / Broad sheen | `.azs-depth-sheen` | One 115-degree white reflection, 4% maximum. Tune `--azs-depth-sheen-opacity: .04`. Static, without backdrop blur. |
| 06 / Tonal ground | `.azs-depth-tonal-ground` | Surrounding plane becomes `#DCE8F5`; surface itself is unchanged. Tune `--azs-depth-ground`. |
| 07 / Light stain | `.azs-depth-stain` | Two broad, static washes: cool blue-grey at up to 5.5%, faint mineral green at up to 3%. Applies to a consumer-supplied light fill; no grain or shadow implied. |

Tonal ground belongs on the surrounding element, not the surface:

```html
<div class="azs-depth-tonal-ground" style="padding: 24px">
  <div class="azs-depth-surface" style="padding: 24px">Azure Sky</div>
</div>
```

## Combine Deliberately

Standard preset: grain + edge light + layered shadow + blue shading. Sheen and
tonal ground start off. Reset restores those four effects and 3% grain. The grain
slider spans 0-8% and is disabled when grain is off. Isolated samples remain fixed
at their documented defaults, independent of combination controls.

```tsx
import "@harness/azure-sky-styling/depth.css";

export function SatinSurface() {
  return (
    <div
      className="azs-depth-surface azs-depth-standard"
      style={{ padding: 24 }}
    >
      Azure Sky
    </div>
  );
}
```

Each effect assigns a separate custom-property slot. The base combines gradient
slots in `background-image` and edge/shadow slots in `box-shadow`; enabling one
does not overwrite the others. Grain has its own pointer-transparent pseudo-element
in an isolated stacking context. Foreground opacity remains 1.

`.azs-depth-standard` selects those same four numbered effect blocks, with no
duplicate recipe. It paints without setting dimensions, borders or radius;
`.azs-depth-surface` adds the optional neutral border and 6px shape in this example.
The expanded form remains `.azs-depth-surface.azs-depth-grain.azs-depth-edge-light.azs-depth-shadow.azs-depth-blue-shading`.

## Standard Gallery Roles

The theme imports the effect stylesheet and applies its standard slots to the
topbar, intro, footer, Cobalt/inverse surfaces, inspector, drawer banner, Cobalt
form and enabled primary buttons. No new wrapper, dimensions or spacing is added.
Existing hover, focus, pressed and disabled rules retain their behavior.

Glass/ghost/danger buttons, disabled controls, semantic status fills and the depth
baseline retain their earlier paint. Palette swatches stay flat and exact; Cloud's
new color is reflected in both its swatch and copied hex value. Pale and secondary
buttons receive the separate light treatment below, never the blue preset.
The study's sliders and toggles affect only its combination preview, not the
gallery's standard. A consuming application's theme is unchanged.

The header's stylesheet download includes both CSS modules and an embedded copy
of the grain PNG, so the downloaded file does not require a separate asset fetch.
Source imports keep the modular files and relative image reference.

Base variables: `--azs-depth-fill`, `--azs-depth-foreground`, `--azs-depth-border`,
and `--azs-depth-radius` (default 6px). Layout, dimensions and padding belong to the
consumer. Blue shading is authored for Cobalt, not a generic theme transformer.

The material owns `background-image`, `box-shadow` and, for grain, `::before`.
Do not combine it with a utility or component rule that independently overrides
those properties or already uses that pseudo-element. Retain the stylesheet's
relative `assets/surface-grain.png` path when copying it without a bundler. Grain
is the only effect requiring an image; the other effects remain CSS-only.

## Light Material

Cloud is `#EFF3F8`, with a cool shaded cast rather than a pure-white fill. Its
palette token is `--azs-cloud`; `--azs-white: #FFFFFF` independently supplies
inverse labels and focus highlights so surface tuning does not dim readable text.
Porcelain and Mist retain their exact base palette values.

Use the stain alone over an existing light background:

```html
<div class="azs-depth-stain" style="background-color: #EFF3F8; padding: 24px">
  Cloud
</div>
```

Use `.azs-depth-light` for stain plus the existing grayscale texture at 2% opacity:

```html
<div class="azs-depth-light" style="padding: 24px; border-radius: 6px">
  Cloud
</div>
```

The light preset supplies Ink foreground, Cloud background, two broad gradient
stains and pointer-transparent grain beneath the text. It adds no shadow, border,
blur, animation or geometry. Grain uses `mix-blend-mode: multiply` within an
isolated stacking context; it shades the pale fill without lowering text opacity.

Tuning points: `--azs-light-fill`, `--azs-light-foreground`,
`--azs-light-grain-opacity` (default `.02`), `--azs-light-stain-layer` and optional
`--azs-light-base-layer`. The stain's 112-degree wash uses blue-grey at 5.5% and
2.5%; its 22-degree wash uses mineral green at 3% and blue-grey at 2.5%. Gradients
fade broadly rather than forming discrete spots. These strengths are intentionally
small; increasing them requires a new text-contrast check.

The theme reuses the stain in its surface, Mist, glaze and page-ground ramps. Grain
is added to pale surface specimens, Cloud/secondary buttons, state/format strips,
drop zones, record/chart panels, overlay readouts, feedback/progress specimens,
composition navigation, collection cards and light material forms. Inputs and
semantic fills remain untextured. Menus and dialogs inherit the stained ramp but
do not receive a new grain layer. The six blue-workbench specimens remain isolated;
the seventh effect is demonstrated on these real light roles and documented here.

## Accessibility and Rendering

- No parent/text opacity, runtime canvas, rendering worker, animated noise, or
  backdrop-filter. The grain PNG is generated once and served as a local asset.
- `prefers-reduced-transparency: reduce` removes grain, sheen and translucent
  edge/shadow layers, including light staining. Opaque blue shading remains.
- `forced-colors: active` uses system foreground/background/border colors and
  removes all decorative images and shadows. These rules do not disable user
  color adjustment.
- White on the brightest measured interior pixel, all effects enabled at 8%
  grain: **5.72:1** in Chromium. This bounds the shipped Cobalt specimen, not
  arbitrary replacement colors or unbounded custom opacity values.
- Standard four-effect specimen at 3% grain: **6.54:1** minimum sampled interior
  contrast. Live desktop measurements found identical pre/post dimensions for
  the header, intro, Cobalt panel, inspector, footer and button-state specimens.
- Stained/grained light specimens: minimum sampled Ink contrast **11.14:1** on
  Porcelain and **10.32:1** on Mist; Steel contrast **4.92:1** and **4.56:1**
  respectively. These measurements cover the shipped defaults, not arbitrary
  custom strengths. Live pre/post dimensions matched for the affected light roles.
- Physical-device paint cost, battery use and other browser engines remain
  unmeasured. Static treatment is a design choice, not a performance benchmark.

## Reproduce

From this component directory, using existing npm dependencies:

```bash
npm run grain:generate
npm run verify:depth-effects
npm run build
npm run verify:depth
```

Generation is optional unless changing the grain algorithm; the bitmap is retained
with source. [ASSETS.md](ASSETS.md) records its seed, dimensions, hash and provenance.

Verified 2026-09-10: 13 CSS/preset cases, 11 depth-study cases and 28 full-gallery
cases passed. The preset matches the four independent effects exactly, the theme
reuses that paint, and reset/copied recipes agree on 3%. Evidence
includes per-effect pixel differences, unchanged sample dimensions, exact isolated
and combined clipboard contents, clipboard refusal recovery, keyboard focus,
minimum contrast, and responsive geometry at 360, 768, 1440 and 1920 CSS pixels.
Automated accessibility scans cover desktop/mobile defaults and the maximum-effect
desktop state. Reduced-transparency and forced-colors fallbacks were exercised.
The existing gallery suite also checks adopted blue roles, preserved exclusions,
exact embedded-asset bytes in downloaded CSS, and plain HTML without JavaScript.
Light checks also cover the independent stain, composed 2% preset, Cloud hex
read-back, unaffected white labels, rendered grain, geometry and contrast.
Live light-material evidence is under `/tmp/azure-sky-light-review/`.

Built-gallery evidence: `/tmp/azure-sky-depth-review/report.json`, full study
captures `depth-<width>.png`, and real-size captures `depth-<width>-viewport.png`.
Full study captures use a temporarily taller viewport; the accompanying viewport
captures preserve the tested size and verify that sticky navigation does not cover
the heading. Override the folder with `AZURE_SKY_DEPTH_ARTIFACT_DIR`.

[Research and sources](research/SURFACE_DEPTH.md) records why these experiments
were selected and separates source findings from proposed design strengths.
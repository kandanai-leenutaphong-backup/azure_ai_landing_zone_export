# Distant Architecture

Five seeded architectural masses behind the gallery's open background. Painterly
mode uses soft masks derived from public-domain Legeay and Challe drawings;
Geometric mode retains the original generated buttresses, terraces and gateways.
The center stays quieter and the bases fade into atmospheric distance. These are
decorative arrangements, not a real place or telemetry visualization.

Open http://127.0.0.1:4317/?architecture=20260910 to reproduce the reference scene.
Without a seed query, each page load obtains a new unsigned 32-bit seed from
`crypto.getRandomValues`. No browser storage or external service is used. Painterly
mode loads three locally bundled masks once; it never fetches museum originals.

## Controls

The building icon beside Density toggles **Distant architecture**. The shuffle
icon, **Generate new distant architecture**, changes the seed and regenerates
the image. Both have named tooltips and keyboard access. Shuffle is disabled while
the backdrop is hidden. Hiding and showing retains the current seed and bitmap;
material controls and scrolling do not regenerate it.

The **Painterly / Geometric** segmented control compares both renderers at the
same seed. Painterly is the gallery default. Add `&architectureStyle=geometric`
to the reference URL to open the earlier procedural-only version. A mask load
failure displays a notification and a geometric fallback; Shuffle retries loading.

The current rendered seed is available as `data-architecture-seed` on
`.azs-distant-architecture`. Set `?architecture=<seed>` to replay it. The query
accepts integers from 0 through 4294967295; missing or invalid values request a
fresh random seed. Shuffle advances the seed by 2654435761 modulo 2^32, but does
not rewrite the URL. Settings last only for the current mounted gallery.

## Source Map

| Responsibility | File |
| --- | --- |
| Seeded geometry, geometric shapes or proportion-preserving mask stamps, atmospheric painting | [frontend/distantArchitecture.ts](frontend/distantArchitecture.ts) |
| Three named local masks and cached image decoding | [frontend/painterlyArchitecture.ts](frontend/painterlyArchitecture.ts) |
| Crop polygons and per-source tonal extraction settings | [scripts/painterly-mask-recipes.json](scripts/painterly-mask-recipes.json) |
| Reproducible source-to-mask generation and alpha checks | [scripts/generate-painterly-masks.mjs](scripts/generate-painterly-masks.mjs) |
| Bitmap lifecycle, viewport resizing and accessibility preference handling | [frontend/DistantArchitecture.tsx](frontend/DistantArchitecture.tsx) |
| Fixed background placement, strength, visibility and compact controls | [frontend/distant-architecture.css](frontend/distant-architecture.css) |
| Gallery seed selection and hide/shuffle controls | [frontend/AzureSkyGallery.tsx](frontend/AzureSkyGallery.tsx) |
| Public exports | [frontend/index.ts](frontend/index.ts) |

`generateDistantArchitecture(seed)` is pure: the same seed produces the same
five-object scene. Each object exposes its kind, position, size, opacity, tier
count and crown proportions. The shape grammar uses filled rectangles, polygonal
buttresses and cut-out arched openings in Geometric mode.

`paintDistantArchitecture(canvas, scene, width, height, tint, masks?)` rasterizes
that scene and returns a PNG data URL. Omitting masks preserves the original
Geometric behavior. Each edifice is painted on a separate scratch
layer before its openings are removed, so a foreground opening does not erase
objects behind it. Vertical alpha gradients hide the bases; a horizontal gradient
reduces contrast through the center. No blur, cloud simulation or procedural noise
field is involved.

Painterly stamps retain their source aspect ratios. The nearest two masses select
vertical masks and scale by viewport-relative height, remaining colossal even on
phones; more distant stamps fit their seeded rectangles. The scene seed selects
the stamps and positions without mirroring the artwork. `source-in` tinting uses
only their alpha, so no original paper color reaches the gallery.

## Mask Recipes

The full-resolution sources are retained unchanged under
[research/painterly/holdings/originals](research/painterly/holdings/originals), with
object-level public-domain records and acquisition hashes in the adjacent catalogue.
The runtime only ships these three derived WebP masks, 501,862 bytes in total:

| Mask | Source / Selected Region | Dimensions | Alpha Levels |
| --- | --- | --- | --- |
| `legeay-temple` | Legeay, Met 343077; upper distant temple | 347x439 | 231 |
| `challe-crowned-hall` | Challe, Met 343439; crowned rotunda and upper hall | 740x960 | 225 |
| `challe-arcade` | Challe, Met 343439; upper arches and piers | 768x305 | 220 |

Each recipe has a normalized polygon, paper/ink quantiles, paper cutoff, gamma,
maximum alpha and bottom fade. The generator removes source colors, preserves
continuous wash/chalk density in alpha, feathers the selection and clears the
outer border. WebP round-trip verification checks every alpha sample, not just a
nonblank file. Crop polygons and extraction are build-time only.

Run `npm run masks:generate` to reproduce them. The generator checks source hashes
against the acquisition catalogue and public-domain status against the saved Met
records. [The generated manifest](frontend/assets/painterly/manifest.json) records
source, recipe, generator and output hashes. The script writes a source/mask
contact sheet to `/tmp/azure-sky-painterly-mask-review/` or
`AZURE_SKY_MASK_ARTIFACT_DIR`. Edit recipes or the generator, never output masks.
Artist and source credits ship in [public/THIRD_PARTY_NOTICES.txt](public/THIRD_PARTY_NOTICES.txt).

## Reuse

```tsx
import { DistantArchitecture } from "@harness/azure-sky-styling";

export function Workspace() {
  return (
    <div style={{ isolation: "isolate", minHeight: "100vh", background: "#EFF3F8" }}>
      <DistantArchitecture seed={20260910} variant="Painterly" />
      <main>Workspace content</main>
    </div>
  );
}
```

Props: `seed: number`, `visible?: boolean` (default true), `tint?: string`
(default `#345A80`, a CSS canvas color), `variant?: "Painterly" | "Geometric"`
(standalone default Geometric for compatibility), and `onFallback?: () => void`.
The gallery explicitly selects Painterly. The caller supplies a light background
and an isolated stacking context. The component renders behind siblings using
`z-index: -1`; content remains above it. Avoid a transformed ancestor that would
change the containing block of its fixed positioning.

Tuning points, all local to the backdrop:

- `planes` in the generator: position, size and opacity for the five distance
  layers. The nearest masses deliberately extend beyond the viewport edges.
- `drawEdifice`: gateway, terraces and buttress shape rules. Changing their
  proportions changes generated architecture, not page geometry.
- `loadPainterlyArchitectureMasks()`: callable cached loader for the optional
  painter argument. The component exposes the rendered style and mask count via
  `data-architecture-style` and `data-mask-count`, including when fallback occurs.
- `distance` and `clearance` gradients: base disappearance and center visibility.
- `--azs-architecture-opacity`: final whole-image strength, default `.85`.
  The generated image itself is already faint; this value is not an 85%-opaque
  silhouette. Increasing strength requires fresh text-contrast checks.

This is a separate backdrop capability, not an eighth material effect. It does
not alter the blue 3% grain preset or the light stain/2% grain preset. The plain
HTML specimen and downloaded material stylesheet contain no architecture generator.
A consuming application's code and theme are not changed.

## Rendering Contract

- Two detached Canvas 2D surfaces generate one cached PNG; the displayed element
  is an empty-alt, `aria-hidden` image, not a mounted canvas. Both surfaces stay
  within a 1600x1100 bitmap box and never exceed the requested CSS dimensions.
- Rendering occurs on mount, seed/tint change, or an observed viewport size
  change, and when the style changes. Identical rounded sizes are ignored. No timer, animation loop, worker,
  scroll handler, or per-device-pixel-ratio oversampling is used.
- Decoding is asynchronous and cached across style/seed changes. An effect cleanup
  invalidates pending callbacks; a late mask load cannot overwrite a newer scene.
  Failed loads clear the cache so an explicit regeneration can retry.
- The render happens synchronously on the main thread. This is bounded work,
  not a zero-cost effect. Development React StrictMode may invoke setup twice.
- `pointer-events: none` prevents interception. Existing opaque working panels
  hide the architecture; it remains visible in open background and through
  existing translucent surfaces. No panel is made transparent for the scene.
- `prefers-reduced-transparency: reduce` and `forced-colors: active` hide the
  decoration and suppress rendering while those preferences are active. Reduced
  motion needs no animation alternative because the scene never animates.
- The depth-study planes use `isolation: isolate` to keep their rounded-edge
  compositing independent of the fixed backdrop. The exact reset-pixel test
  remains unchanged and passes.

## Verification

From this component directory, using the installed dependencies:

```bash
npm run masks:generate
npm run verify:architecture-generator
npm run build
npm run verify:architecture
npm run verify:depth
npm run verify
```

Verified 2026-09-11: source/mask checks, 13 architecture cases, 11 depth-study cases
and 28 gallery cases passed. Architecture acceptance covers seed/bitmap replay,
regeneration, visible background pixels, no geometry shift from hiding the scene,
zero image-source writes during material interaction and scrolling, text contrast,
keyboard controls, style switching, cached masks, failed-load retry, stale-load
protection and accessibility fallbacks. The generator also checks that foreground
architecture remains visible below the mobile header and that masks match their
source/recipe/output hashes.

Framing and control checks cover 360x800, 768x1024, 1440x900 and 1920x1080 CSS
viewports. The largest viewport generates a 1600x900 image. Automated accessibility
checks include the new controls on desktop and mobile; the existing gallery suite
also runs its full-page scans and JavaScript-disabled plain HTML check.

The original Geometric check measured 643,672 nontransparent pixels and maximum
alpha 26/255 at 1440x900 before the CSS strength multiplier. The Painterly reference
seed's minimum sampled exposed-label contrast is 4.60:1 at 1440x900. These
are measured reference-scene values, not a proof for every seed, tint, strength,
screen or font configuration. Keep the default strengths restrained.

Evidence: `/tmp/azure-sky-architecture-review/report.json`,
`generator-1440.png`, and `architecture-<width>.png`. Override the browser evidence
folder with `AZURE_SKY_ARCHITECTURE_ARTIFACT_DIR`. The report includes actual
per-render timings; physical-device performance and battery use are unmeasured.
Deterministic bitmap equality is established on the installed Chromium toolchain,
not promised across browser engines or encoder versions.

[Painterly reference shortlist](research/painterly/README.md) retains four inspected
public-domain artworks. Two supplied the derived architectural masks; Turner and
Cole remain references only. Original paintings are never bundled into the app.
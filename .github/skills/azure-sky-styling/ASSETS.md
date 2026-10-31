# Azure Sky Asset Register

## Current Surface

The cloud experiment was removed on 2026-09-10 at the user's request. No cloud
renderer, laboratory, worker, scene exporter, generator, or PNG/WebP scene asset
remains. The Azure Sky palette, font families, icons and data graphics are retained.
The original image references informed the palette only and were never distributed.

## Distant Architecture

A separate, original distant-architecture generator was added on 2026-09-10. It
does not restore the cloud renderer or any retired image input. Geometry is
generated from a 32-bit seed, then painted on detached Canvas 2D surfaces into one
PNG data URL. Geometric mode uses original gateway, terrace and buttress rules.
Painterly mode, added 2026-09-11 and selected initially by the gallery, uses local
alpha masks derived from two public-domain museum images.

| Derived Mask | Artist / Met Object | Dimensions | Bytes |
| --- | --- | --- | --- |
| [legeay-temple.webp](frontend/assets/painterly/legeay-temple.webp) | Jean Laurent Legeay, *Architectural Fantasy*, ca. 1785-90 / 343077 | 347x439 | 59,134 |
| [challe-crowned-hall.webp](frontend/assets/painterly/challe-crowned-hall.webp) | Charles Michel Ange Challe, *Architectural Fantasy*, 18th century / 343439 | 740x960 | 324,996 |
| [challe-arcade.webp](frontend/assets/painterly/challe-arcade.webp) | Charles Michel Ange Challe, same work / 343439 | 768x305 | 117,732 |

The full-resolution source images are 3294x3320 and 3811x2455, respectively.
Both object records identify the works as public domain, and the mask generator
re-asserts that flag before producing any output. Original URLs,
retrieval timestamps and hashes are retained in the
[acquisition catalogue](research/painterly/holdings/catalogue.json); the rights
basis and its limits are stated in [RIGHTS.md](research/painterly/RIGHTS.md).

Modifications: selected architecture, paper/color removal through tonal-to-alpha
extraction, feathered borders, bottom fades and azure tinting at runtime. The
[mask manifest](frontend/assets/painterly/manifest.json) links every output to its
source and generator hashes. Reproduce with `npm run masks:generate`; retained
originals stay outside the bundle. Three masks total 501,862 bytes and load once
from the application origin. Credits ship in `public/THIRD_PARTY_NOTICES.txt`;
neither the artists nor the museum endorses the gallery.

The current image is held in component state, not stored in the repository or
downloaded from a server. Seed, viewport size and tint define the result; the
bitmap fits within 1600x1100 pixels. Per-image hashes are not a static asset
manifest: seed replay and byte equality are checked on the installed Chromium.
The displayed image is decorative, and regenerates only when needed.

[DISTANT_ARCHITECTURE.md](DISTANT_ARCHITECTURE.md) records crop recipes,
reproduction, controls, size bounds and accessibility/performance limits. No new
runtime package was introduced. Public-domain image derivatives are separately
credited rather than described as wholly original generated artwork.

## Static Surface Grain

The surface-depth study adds one original grayscale microtexture, not scenery.

| Property | Value |
| --- | --- |
| File | [frontend/assets/surface-grain.png](frontend/assets/surface-grain.png) |
| Dimensions | 128x128 pixels |
| Encoded size | 26,662 bytes |
| SHA-256 | `9403025a0503e882c4af41fd5f008c67d7049b360b18d1383bf5ab204da6bfcb` |
| Seed | `0x415A5552` |
| Source | Original seeded xorshift grayscale samples, encoded with the installed Playwright Chromium; no retrieved pixels |
| Generator | [scripts/generate-grain.mjs](scripts/generate-grain.mjs), run with `npm run grain:generate` |
| Runtime | Local repeating CSS background: 3% on blue roles/depth specimens, 2% with multiply blending on light roles; the grain itself requires no runtime generator, canvas or worker |

The generator is reproducible from source with the pinned browser toolchain.
Encoding bytes can vary with a different browser version; the retained bitmap is
the build input. Vite fingerprints it and rewrites the CSS URL. Preserve the
relative asset path when consuming the stylesheet without a bundler. No new
third-party artwork or asset license was introduced.

## Fonts

Self-hosted through local npm dependencies, with Latin subsets bundled by Vite.
No Google Fonts request or other runtime font CDN is used. Package versions are
pinned in `package-lock.json`; upstream license files remain in each package.

| Font | Weights | Package | Upstream |
| --- | --- | --- | --- |
| Barlow Condensed | 600 | `@fontsource/barlow-condensed` | https://github.com/jpt/barlow |
| IBM Plex Sans | 400, 500, 600 | `@fontsource/ibm-plex-sans` | https://github.com/IBM/plex |
| IBM Plex Mono | 400 | `@fontsource/ibm-plex-mono` | https://github.com/IBM/plex |

All three font families use the SIL Open Font License 1.1. No font outlines were
modified. Consumer applications supply the same font families when importing only
the portable stylesheet.

`public/THIRD_PARTY_NOTICES.txt` preserves complete upstream notices for the direct
runtime dependencies, including the fonts. Vite copies it to the production output
unchanged. Retain it when redistributing the demo or its fonts, and update it when
dependency licenses change.

## Icons and Data Graphics

- Interface icons: `lucide-react`, ISC with Feather MIT portions, https://lucide.dev. No hand-drawn
  replacement toolbar icons. Exact version in `package-lock.json`.
- Area, line, bar, donut, scatter: Recharts, MIT license, https://recharts.org.
  Values are fixed synthetic fixtures, not telemetry or measured service metrics.
- Relationship diagram: fixed illustrative topology in `Visualizations.tsx`,
  ordinary SVG edges and labeled HTML buttons. No physics, inferred graph,
  or automatic graph-layout algorithm.
- Heatmap: deterministic synthetic cell values with textual read-back.
- Source preview: a fixed, explicitly colored code specimen, not a general
  syntax-highlighting engine. Diff content is also a fixed specimen.
- Avatars: synthetic initials, not photographs or identifiable people.

## Historical Research

[CLOUD_RESEARCH.md](research/CLOUD_RESEARCH.md), its source list and measured results
are historical records, not current features or runnable benchmark claims. The
independent HyperFrames adapter now lives in `.github/skills/hyperframes-motion`;
it has no runtime or build dependency on this gallery. No HyperFrames video runtime
or CLI was installed for the removed experiment.
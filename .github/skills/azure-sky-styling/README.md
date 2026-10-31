# Azure Sky

An isolated, interactive visual proof of concept for the Azure Sky palette,
typography, and component styling. Includes a gradient/translucency/layering study
with subtle mint and cool mist highlights. Blue-white gradation and lightly glazed
backgrounds extend across the gallery. No orange accents or cloud scenery.
Blue surfaces and enabled primary buttons use the standard material: static grain
at 3%, edge light, layered shadow and blue shading.
Light panels and pale buttons carry cool staining with 2% grain. Cloud is shaded
off-white rather than pure white; inverse text retains an independent white token.
A separate surface-depth workbench compares six modular effects with labeled
isolated samples, copyable recipes and a configurable combination.
Seeded silhouettes of monumental architecture sit faintly behind open background:
Painterly mode stamps local masks derived from public-domain Legeay/Challe art;
Geometric mode retains procedural forms. No ships or animated clouds.
**All data and people are synthetic.** No application code, authentication, deployment,
source input, or live datastore is changed or accessed by this demo.

## Run

Node 20.20+ and npm. No Python environment, cloud identity, or API key required.
From this directory:

```bash
npm ci
npm run build
npm run dev
```

Open http://127.0.0.1:4317/. Vite refuses a busy port; use
`npm run dev -- --port 4319` when 4317 belongs to another process. Stop with Ctrl+C.
The development server binds only to loopback. This is not a deployment entry point.

The atlas includes a link to `plain.html`: a separate HTML/CSS specimen with native
controls and **no React, Tailwind, or JavaScript runtime**. It also builds as its own
entry point. Open it directly after `npm ci`, or through the same server.

## Contents

| Section | Specimens |
| --- | --- |
| Foundations | Copyable palette, Porcelain/Mist/Cobalt surfaces, typography, pinning, contrast reference; adjustable material study; six isolated surface-depth effects and combined preview |
| Controls | Action variants and sizes; default/hover/focus/active/disabled/busy strip; form validation; search/datalist; password reveal; dates; readonly/disabled/invalid fields; textarea; checkbox/radio/switch; slider; stepper; tags; format toolbar; file selection/drop |
| Data | Derived fixture totals; huge/decimal/missing values; sortable/filterable table; selection; CSV export; pagination; responsive column visibility; inspector; empty search recovery |
| Visualizations | Area/line/bar switch; series toggles; donut; scatter; fixed network selection; heatmap read-back; timeline; text values |
| Overlays | Accessible modal; duplicate/empty-name refusal; local collection create/remove; confirmation/cancel; drawer; date popover; menu; tooltip; keyboard command palette |
| States | Success/info/warning/error; skeleton; loading; empty-to-populated action; simulated timeout/retry; progress/pause/completion; dismissible notifications |
| Compositions | Report/workspace/settings tabs; sidebar; breadcrumbs; archive; avatars; collection cards; file list; prose/quote; fact-versus-interpretation; static code/diff; accordions; inverse form |

Density switches between comfortable and compact table spacing. The seven sections
remain interactive, including local saves, export, validation, dialogs and recovery.
The building and shuffle icons beside Density hide/show and regenerate the distant
architecture. Painterly/Geometric compares both at the same seed; Painterly starts
selected. [DISTANT_ARCHITECTURE.md](DISTANT_ARCHITECTURE.md) owns the generator,
seed replay, component API and measured browser evidence.

The header's **Material study** link opens `#materials`. The header uses the standard
textured blue material, faint mint detail, and a translucent white-on-blue
link. The sticky section navigation uses a 94-97% opaque cool gradient with an 8px
backdrop blur; it remains readable without blur support. Shared ramps extend into
tables, chart surfaces, inspectors, cards, dialogs, and composed workspaces. Input
fields and semantic status colors retain their existing readable fills.

The cloud experiment was removed on 2026-09-10 at the user's request: laboratory,
renderer, worker, controls, scene exports, image files, generation/benchmark scripts,
and motion-only tests. The palette, fonts and other gallery specimens remain.
[Earlier research](research/CLOUD_RESEARCH.md) and its measurements are retained as
historical records, not runnable features. The independently copied HyperFrames
workflow is now owned by the separate HyperFrames Tools library; it is not a gallery dependency.

## Contract and Reuse

Skill-owned package: `@harness/azure-sky-styling` under `.github/skills/azure-sky-styling`.
`npm run build:library` emits ESM and declarations; `npm pack` includes CSS/assets, all required
notices and retained rebuild inputs. React/React DOM 19 are peers; Radix, Lucide, Recharts and
Fontsource packages remain declared dependencies. No npm registry publication is claimed.

```tsx
import { AzureSkyGallery, DistantArchitecture } from "@harness/azure-sky-styling";
import "@harness/azure-sky-styling/styles.css";
```

- Theme CSS authority: `frontend/azure-sky.css`. Tokens use `--azs-*`; theme rules
  are scoped to `.azure-sky`. The separate depth stylesheet uses opt-in
  `azs-depth-*` classes and works without that root. Neither adds a global reset.
- React public surface: `frontend/index.ts` exports `AzureSkyGallery`,
  `DistantArchitecture`, the cached painterly loader, seeded generator/painter and types.
  Import the package stylesheet explicitly. Gallery workflows remain synthetic prototypes,
  not production service APIs.
- Package exports: `.` for the gallery, `./styles.css` for theme CSS consumers,
  `./depth.css` for standalone depth effects, `./THIRD_PARTY_NOTICES.txt` for notices.
- Plain HTML consumers wrap markup in `.azure-sky`, link the stylesheet, and supply
  the documented fonts. The source theme imports `depth-effects.css` and its local
  grain image. The header's stylesheet download embeds both dependencies into one
  CSS file. Tailwind is not required to consume the style.
- The demo owns React 19, TypeScript strict, Vite 6, Tailwind 4, Radix primitives,
  Lucide icons, Recharts, and locally bundled fonts. No reverse dependency on a consuming application.
- Source fixtures: `frontend/fixtures.ts`. Chart units and metrics are demonstrative.
- Browser-local persistence keys: `azure-sky:density`,
  `azure-sky:workspace`, `azure-sky:collections`. Workspace name and collection list
  are read back after saving. Other specimen changes are session-only.
- Distant architecture chooses a random seed per mount, or replays the unsigned
  integer supplied by `?architecture=<seed>`. Add `&architectureStyle=geometric`
  for the earlier procedural mode. Painterly loads three local masks once; a
  failed load shows a geometric fallback and notification, and Shuffle retries.
  It is hidden for reduced-transparency
  and forced-colors preferences. Its two generation canvases are detached; the
  background displays one cached image, with no continuous rendering.
- File selection validates the extension and displays the local filename. It never
  uploads, parses, executes, or retains file content.
- No backend or authenticated automation contract is claimed. Substantial behaviors
  here are bounded demo fixtures; production application APIs remain deferred.

## Migration Verification

2026-09-16: ESM/declaration and gallery builds passed on Node 20.20. The gallery imports the public
package. Existing browser verification passed 28 cases at 360, 768, 1440 and 1920px with no runtime
errors; architecture verification passed 13 cases, including asset fallback, seed replay and pixels.
Generator checks verified retained source/mask hashes and deterministic geometry/pixels. Separate
local assets are preserved; npm packaging does not inline masks into the JavaScript bundle.

Historical framework scope: F2 ESM/types/CSS/assets and F8 public exports/examples are covered. F3 styling is
explicitly opted in; host business authorization is not supplied. F4 uses React/UI/native generator
contracts, with no service result wrapper. F5 UI lifetime is React-owned; F6 canvas/generator bounds
remain local, while a shared service budget is not applicable to styling. F7 synthetic browser state
remains with the gallery and claims no backend persistence. The [catalogue](../../../libraries/capabilities.json)
now registers this as a skill only; [conformance](../harness-guide/framework/CONFORMANCE.md) records the prior artifact scope.
Existing font/artwork rights and rebuild inputs are retained.

## Visual Specification

| Token | Value | Purpose |
| --- | --- | --- |
| Cloud | `#EFF3F8` | Shaded off-white surfaces and light material base |
| White | `#FFFFFF` | Highlights, inverse text and light focus outlines; separate from Cloud |
| Porcelain | `#F7FBFF` | Reading/input surfaces |
| Mist | `#EAF3FF` | Workspace canvas |
| Open Sky | `#4F8ED8` | Atmospheric identity |
| Action Azure | `#2463B3` | Actions, selection and links |
| Cobalt | `#123F91` | Structural/inverse surfaces |
| Naval Ink | `#102D50` | Primary text |
| Steel | `#456487` | Secondary text |
| Fine Line | `#B8CEE5` | Decorative separators only |
| Control Edge | `#6C87A5` | Meaningful control boundaries |
| Mint / Mint Ink | `#E5F1EC` / `#34594F` | Faint green selection tint and readable foreground; blends toward Porcelain |
| Success / warning / error | `#0D756C` / `#986300` / `#B5364A` | Semantic exceptions, always with text/icon cues |

Fonts: Barlow Condensed 600 for display; IBM Plex Sans 400/500/600 for interface;
IBM Plex Mono 400 for identifiers. Zero letter spacing. No viewport-scaled type.
Desktop controls start at 36px; primary mobile targets at 44px. Compact/comfortable
table rows use 36/44px minimums, expanding for multiline content. Radii: 4px controls,
6px repeated items, 8px dialogs. Overlay shadow: `0 8px 24px rgb(16 45 80 / 12%)`.
Motion: 120ms control and 180ms overlay transitions; reduced motion disables all
CSS animations/transitions. No cloud canvas, rendering worker, or scene animation
is mounted or bundled.

Calculated contrast: Ink/Porcelain 13.35:1; Steel/Porcelain 5.90:1;
White/Action Azure 5.98:1; White/Cobalt 9.79:1; Control Edge/Porcelain 3.58:1.
White/Open Sky is only 3.39:1, so Open Sky is not an ordinary white-label button fill.

Palette gradient tokens remain `--azs-surface-ramp` (Cloud to Porcelain to Mist),
`--azs-mist-ramp` (pale blue to Porcelain), and `--azs-cobalt-ramp` (Cobalt to Action
Azure). Standard blue roles use the depth module's shading and shadow slots instead
of the original Cobalt ramp. The surface/Mist/glaze ramps include faint cool stain
layers. `--azs-surface-glaze` blends 94-82% opaque Cloud/blue backgrounds on the known
light gallery canvas; use opaque ramps over unknown content. Gradation lives in the
surface background, never parent/text opacity. Dialog and popover gradients are
opaque, and palette swatches remain flat to display their exact color values.

## Material Study

`frontend/Materials.tsx` owns the experiment inside Foundations. It adds no
dependency, worker, canvas, image asset, or persistent browser state. Changes stay
within the study; Reset restores its design controls and Copy exports its CSS
variables and ground/highlight attribute values to the clipboard.

| Control | Range / Default | Effect |
| --- | --- | --- |
| Gradation | 0-100% / 60% | Blue-to-white gradient strength on the preview ground |
| Surface opacity | 65-100% / 82% | Front sheet background alpha, never parent/text opacity |
| Layer separation | 0-24px / 16px | Near sheet offset and twice that offset for the rear sheet |
| Highlight | Mint or Mist / Mint | Subtle selected-reference gradient, marker and readable foreground |
| Ground | Porcelain or Cobalt / Porcelain | Light and dark comparison conditions |
| Frosted surface | On/off / On | 10px or 0px backdrop blur on the foreground sheet |

Reusable styles stay in `frontend/azure-sky.css`: `--azs-material-strength`,
`--azs-material-alpha`, `--azs-material-gap`, and `--azs-material-blur` have CSS
defaults on `.azs-material-study`. `data-highlight` and `data-ground` select the
documented variants. Rear sheets contain no meaningful text and cannot intercept
pointer events. Fixed space reserves the maximum offsets rather than cropping them.

Accent roles are aesthetic emphasis, not new evidence states: subtle mint or mist
identifies a selected/pinned reference. Commands use blue or pale/glass treatments;
the orange and apricot tokens, buttons and backing-layer tint have been removed.
Success, warning and error retain their original tokens, labels and icons.

Calculated text contrast: Mint Ink/Mint **6.74:1**; Steel/Mist **5.48:1**. Ink on 65% Porcelain
composited over Cobalt is **7.00:1**. Secondary text on the unstained pale-blue ramp's
darkest stop is **5.10:1**; inverse secondary text on the original Cobalt ramp's lightest
stop is **5.34:1**. The standard blue material's measured contrast is recorded below.
That bound covers these controlled preview backgrounds, not arbitrary photographs
or a different theme. Text stays fully opaque. Blur is optional visual treatment,
not a requirement for contrast. No per-frame CSS animation or blanket `will-change`
was introduced; physical-device blur performance remains unmeasured.

## Assets

[ASSETS.md](ASSETS.md) records local fonts, icons, data graphics and the original
128x128 static grain texture reused by the depth specimens, blue and light roles.
`public/THIRD_PARTY_NOTICES.txt` preserves upstream notices and ships with the build.
Three artist-derived WebP masks (501,862 bytes total) ship locally with credits;
their museum originals are retained for reproducibility but excluded from the
build. [research/painterly/RIGHTS.md](research/painterly/RIGHTS.md) states the
per-artifact rights basis: public-domain images, CC0 1.0 object metadata, and
what neither instrument grants. Distant architecture is composed in memory from
its seed and displayed as a cached PNG. No museum or other external service is
contacted at runtime.

## Surface Depth

The header's **Surface depth** link opens `#depth`. Six independently labeled
techniques: static grain, directional edge light, layered blue shadows, blue
shading, broad sheen and tonal ground. Baseline and combined specimens preserve
identical dimensions and text. Default combination uses the first four techniques;
sheen and tonal ground remain optional. Grain ranges from 0-8%, default 3%.

The same four-effect preset is now standard on the header, intro, footer,
Cobalt/inverse surfaces, inspectors, drawer banners, Cobalt forms and enabled
primary buttons. Layout, semantic colors, disabled/ghost/danger/glass buttons and
the depth baseline remain unchanged. Exact palette swatches remain flat; Cloud's
shade is now `#EFF3F8`.

Light roles use a separate `.azs-depth-light` preset: cool blue-grey staining,
faint mineral-green tint and 2% grain. `.azs-depth-stain` isolates just the gradient
treatment. Pale panels and Cloud/secondary buttons carry this finish; inputs stay
clean and inverse labels stay white. Neither light effect enables the blue preset
or changes the depth-workbench controls. The effect guide includes both recipes.

[DEPTH_EFFECTS.md](DEPTH_EFFECTS.md) maps every effect to its named CSS block,
tuning variables and isolated HTML/React recipe. Paint, recipe registry and demo
layout live in separate files. Copy buttons produce isolated or combined HTML;
clipboard refusal opens the exact recipe for selection. Changes are session-only,
and Reset restores the standard combination at 3%. Study controls do not modify
the material elsewhere in the gallery. Use `.azs-depth-standard` to reuse the
preset without duplicating its four constituent rules.

Verification: `npm run verify:depth-effects` passes 13 isolated CSS/preset cases;
`npm run verify:depth` passes 11 production-browser cases, including pixel changes,
responsive bounds, copy/reset and failure recovery, keyboard focus, automated
accessibility and reduced-transparency/forced-colors fallbacks. Minimum measured
white-text contrast at maximum grain with all effects: 5.72:1; at the standard
four-effect 3% setting: 6.54:1 in the sampled specimen. Evidence and
physical-device limitations are in the effect guide.

Measured light-material contrast: Ink **11.14:1** on Porcelain, **10.32:1** on Mist;
Steel **4.92:1** and **4.56:1** respectively. Grain visibly changes pixels while
the measured light-panel and control dimensions remain unchanged. These values
apply to the shipped staining and 2% grain, not stronger custom treatments.

## Verify

```bash
npm run build
npm run verify:depth-effects
npm run verify:depth
npm run verify:architecture-generator
npm run verify:architecture
npm run verify:security-review
npm run verify
```

`security-review.html` is a third build entry point: an isolated application-shaped
preview (scanner, tool board, review-agent chat, explorer) reached from the atlas
header's **Security review preview** link. Its data, agent responses and sources are
local synthetic fixtures; no service, model or datastore is contacted.
`npm run verify:security-review` drives its real controls across four viewports and
saves evidence under `/tmp/azure-sky-security-review/`.

The verifier launches an isolated production preview on an ephemeral loopback port,
drives the real controls, checks persisted data/download contents, confirms absent
cloud canvases/workers and valid section links, and saves browser evidence under
`/tmp/azure-sky-review/`. Override with
`AZURE_SKY_ARTIFACT_DIR=/absolute/output/path`. Server and browser close on success or
failure. A failed assertion exits nonzero; the last successful case identifies the
boundary. Read `failure.json` and fix the named case before rerunning.

Tests require Chromium for the pinned Playwright package. If absent,
`./node_modules/.bin/playwright install chromium` installs that browser.

Review targets: 360x800, 768x1024, 1440x900, 1920x1080, and 200% layout zoom.
Automated checks do not replace a human screen-reader session, physical touch-device
testing, or cross-browser certification. This is a reviewable style prototype, not
an adopted application theme or a production design-system release.

Verified 2026-09-10: production typecheck/build passed; `npm run verify` passed 28/28
cases with zero runtime errors. Report, Workspace and Settings each passed automated
WCAG A/AA scans at 1440px and 360px. Four viewport widths had no page overflow or
clipped headings/control labels; measured primary mobile targets met 44x44px. Dialog
focus containment/return and mobile bounds passed. The plain HTML specimen worked
with JavaScript disabled. No cloud canvas, worker, or laboratory link remains.
Material tests operate all settings, copy/reset, pinning and the next-action button;
check known-background contrast bounds; and prove layer containment at the four
viewports and 200% layout-zoom equivalent. The minimum-opacity, maximum-offset
variant passed automated accessibility scans on desktop and mobile. Computed
geometry and a viewport capture, not tall element captures alone, establish that
the translucent layers leave text and controls visible and hit-testable.
Regression checks also reject orange accent tokens/controls, verify the lighter mint,
and assert shared gradation and fully opaque foreground content across working surfaces.

The zoom check emulates a 1440x900 physical display at 200% layout zoom using a
720x450 CSS viewport and 2x device-pixel ratio. It verifies reflow and operation,
not the browser chrome's native zoom shortcut. Automated accessibility passes are
not a claim of complete accessibility certification; incomplete automated checks
remain subject to human review.
# Efficient Procedural Clouds

**Historical record.** The cloud experiment was removed on 2026-09-10 at the user's
request. Renderer, laboratory, assets, benchmark runner and motion-only tests are
no longer present. The research and measured results below describe the 2026-09-09
experiment; recommendations are not the current product direction.

**Yes: browser-side procedural clouds are practical. Generate detail once per seed,
then animate cached layers. For this UI, translucent puff clusters are the cheaper
generation option; full volumetric raymarching is unnecessary.**

Research and measurement: 2026-09-09. Ships, structural geometry, skyline, and their
controls were removed. The laboratory compared `Detailed` and `Soft puffs`.
Detailed was the default for visual continuity; neither mode used image inputs.

## Techniques and Evidence

| Approach | Evidence | Decision for Azure Sky |
| --- | --- | --- |
| Cached Canvas noise textures | [MDN Canvas optimization](https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API/Tutorial/Optimizing_canvas) recommends pre-rendering repeated drawing into an offscreen canvas and reusing it. | Already implemented: generate cloud density and lighting per seed; reuse generated textures for drift and subtle pose blending. |
| Translucent circles/ellipses | Ordinary Canvas paths and alpha blending can compose a cloud silhouette. The same caching guidance applies. | Implemented as `Soft puffs`: 25 overlapping white/near-white radial circles per cloud, varying radius, placement and opacity. Each cluster is generated into one 320x288 in-memory sprite. Gradients are not rebuilt every frame. |
| DOM/CSS cloud layers | [web.dev animation guidance](https://web.dev/articles/animations-guide) recommends transform/opacity animation and inspecting repaint behavior. Composited layers can avoid repeated paint. | Viable for a few decorative layers; animate whole generated cloud groups, not hundreds of DOM nodes. Actual compositor promotion, layer memory, and frame cost are unmeasured here. |
| GPU 2D procedural noise | [The Book of Shaders, fBm](https://thebookofshaders.com/13/) explains octave-based noise and domain warping, including cloud-like patterns. | Viable if continuously evolving internal texture is worth a shader path. Bound output resolution and octave count. No WebGL/WebGPU shader implementation or performance result is claimed in this change. |
| GPU volumetric raymarching | [Maxime Heckel's cloudscapes article](https://blog.maximeheckel.com/posts/real-time-cloudscapes-with-volumetric-raymarching/) demonstrates animated cloud volumes and discusses sample counts, reduced-resolution rendering, dithering and upscaling. | Possible, but a different cost class: repeated density/light samples per pixel. Defer for this work-focused style prototype. Published demo timings are not portable to this machine or a phone. |
| Worker/OffscreenCanvas execution | [MDN OffscreenCanvas](https://developer.mozilla.org/en-US/docs/Web/API/OffscreenCanvas) documents worker rendering and transferable frames. | Keeps generation off the main thread. It moves work; it does not erase CPU/GPU or bitmap-transfer cost. |

Circle clusters should overlap into a cloud mass, not remain isolated dots. A few
larger lobes establish the silhouette, smaller lobes break its outline, and lower
opacity lets the sky supply soft internal blue shadows. Different speeds between
cloud banks imply depth. This is intentionally illustrative, not fluid simulation.

## Measurements

Source: [benchmark-results.json](benchmark-results.json). The removed benchmark
runner measured one built worker/canvas at a time;
three seeds per mode/size; five warm-up frames per seed, then 30 serial unpaced
frames per seed. Cached percentiles use 90 samples and nearest-rank selection.

Environment: Chromium `151.0.7922.34`, Node `20.20.0`, Linux/WSL2, AMD Ryzen AI MAX+
395 host, 32 logical CPUs. The browser reports ANGLE/SwiftShader for WebGL. This is
not evidence of the hardware-GPU Canvas path, mobile hardware, battery use, or
browser refresh-rate performance. Only one local run is recorded.

| Canvas | Mode | Generation Median | First-Frame RPC Median | Cached Draw+Transfer Median / P95 | Cached RPC Median / P95 |
| --- | --- | --- | --- | --- | --- |
| 360x420 | Detailed | 332.5 ms | 336.1 ms | 3.2 / 4.3 ms | 3.5 / 4.8 ms |
| 360x420 | Soft puffs | 3.7 ms | 18.7 ms | 1.6 / 2.8 ms | 1.9 / 3.0 ms |
| 1440x470 | Detailed | 280.5 ms | 292.3 ms | 10.0 / 15.9 ms | 10.5 / 16.3 ms |
| 1440x470 | Soft puffs | 2.9 ms | 23.0 ms | 7.9 / 10.8 ms | 8.3 / 11.3 ms |
| 1600x750 | Detailed | 344.5 ms | 374.9 ms | 15.5 / 23.3 ms | 15.9 / 24.0 ms |
| 1600x750 | Soft puffs | 3.7 ms | 33.3 ms | 12.5 / 16.7 ms | 12.9 / 17.3 ms |

Timing boundaries matter:

- Generation is the worker's `generateSky` call. Canvas may defer raster work;
  the first-frame round-trip is the more useful startup observation. Do not claim
  a complete visible cloud frame from the 2.9 ms generation number alone.
- Worker draw+transfer includes `drawSky` and `transferToImageBitmap`.
- RPC includes worker messaging/queueing until the frame arrives. The first seed
  also includes worker startup and module loading. No cache-hit generation is
  counted as a cold generation sample.
- Main-thread `drawImage` submission is measured separately in the JSON. Neither
  it nor RPC measures final GPU completion or display scanout. These are not FPS.
- Detailed always ran before Soft puffs for each size. Three cold samples are
  enough for a local comparison, not a device-general latency guarantee.

## Recommendation

1. Keep the present worker-generated, cached-layer design. It is genuinely
   procedural despite retaining intermediate textures in memory: the source is
   seed/shape/noise parameters, not a shipped bitmap.
2. Prefer `Soft puffs` when rapid seed/coverage changes and a quiet abstract style
   matter most. Keep `Detailed` for textured illustration. Most measured savings
   occur at generation; steady-state cost still rises with canvas pixel count.
3. Retain bounded 30fps scheduling, capped resolution, pause, reduced motion and
   hidden/offscreen suspension. A worker can protect input responsiveness while
   still consuming substantial resources; hidden views must not keep rendering.
4. If a production background needs less steady-state cost, first test a small
   set of generated cloud layers animated with CSS transforms/opacity, or direct
   worker ownership of the visible canvas to avoid a bitmap message every frame.
   Both remain unimplemented alternatives, not proven optimizations in this run.
5. Add a GPU noise path only after measuring the intended hardware. Do not rebuild
   multi-octave CPU noise for every pixel of every animation frame.

## Archived Evidence

The benchmark is no longer runnable from the current component. The retained JSON
identifies the measured worker and its SHA-256. Results are not evidence for the
current gallery, which has no cloud rendering. The source acquisition commands
below remain independent of the retired implementation.

Sources are enumerated in [cloud-sources.txt](cloud-sources.txt). No ranked search
provider was configured, so known primary documentation was fetched directly:

Current commands require installed `webres` and `LIBRARY_ROOT` set to the Azure Sky library.
Refreshing sources is separately authorized acquisition, not part of a build or migration test.

```bash
python3 -m webres.cli.fetch_page \
  --urls "$LIBRARY_ROOT/research/cloud-sources.txt" \
  --subject procedural-cloud-efficiency \
  --out /tmp/azure-sky-cloud-sources/pages \
  --catalogue /tmp/azure-sky-cloud-sources/catalogue.json
python3 -m webres.cli.catalogue \
  --catalogue /tmp/azure-sky-cloud-sources/catalogue.json --verify
```

The original acquisition also generated
text extracts; their catalogue entries were derived from the fetched HTML entries
with the same source URL/time and new byte hashes. Its final verified catalogue is
`/tmp/azure-sky-cloud-research/pages/catalogue.json`: ten entries, zero missing,
changed, uncatalogued, or source-less files. Fetched third-party pages stay outside
the repository and are not runtime assets. This note paraphrases their technical
claims; no source code was copied from them.

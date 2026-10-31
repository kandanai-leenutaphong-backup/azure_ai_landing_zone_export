# Gates and evidence

Every command runs through the library's [scripts/hf.mjs](../scripts/hf.mjs), with explicit absolute
`--root` and `--runtime` directories before `--`. The wrapper allowlists exact command shapes and
refuses everything else before the CLI is spawned. Render requires `--allow-render`; browser
installation requires `--allow-browser-install`.

## Command shapes

| Purpose | Shape |
| --- | --- |
| Static contract | `lint <project> --json` |
| Transition control | `check <project> --json --snapshots --at-transitions` |
| Beat sampling | `check <project> --json --snapshots --at <csv>` |
| Render | `render <project> --quality draft\|high --fps 30 --output <output>` |

Project and output paths are work-root-relative; absolute paths, escaping symlinks and `..`
segments are refused. `--at` timestamps are unsigned decimals matching
`^\d+(\.\d+)?$` — no sign, exponent, whitespace or empty field — strictly
increasing, at most twenty, each at least zero and strictly less than the
root's `data-duration`, which itself may not exceed eight seconds. The wrapper
re-emits the parsed numbers canonically as a single argument.

## Sampling plan

`--at-transitions` returns zero samples for CSS motion. Record that as the
expected control result; it is not coverage. Coverage comes from the explicit
CSV, which must place at least one timestamp strictly inside every beat named
in the beat map. Any beat without a sample is reported.

## Evidence layout

Under the evidence directory you were given:

| Path | Contents |
| --- | --- |
| `<composition>.beats.json` | Beat map, written before authoring |
| `lint-passN.json` | Every lint pass, including failures |
| `check-passN.json` | Every check pass, including failures |
| `snapshots-passN/` | The snapshots from that pass, copied immediately |
| `snapshots/<composition>/transitions/` | Transition-sampled set |
| `snapshots/<composition>/explicit/` | Explicit-timestamp set |
| `render-*.log` | Draft and final render logs |
| `*.ffprobe.json` | Codec, duration, dimensions, frame rate |
| `frame-hashes.json` | Decoded-frame hashes from both renders |

Copy snapshots out before the next check runs. Overwritten failing frames
cannot be recovered and they are the most informative evidence in the run.

## Network sweep

Search every check stderr and every render log for `Google Fonts`, `Fetched`,
and `http`. Quote what you find. A remaining fetch is a named tool exception,
not a clean footprint, and a sweep of only one log is not a sweep.

## Determinism proof

Render final twice. Decode both at fixed timestamps derived from the duration,
using identical argument order (`-ss` before `-i`, one frame, raw RGB24), and
require matching SHA-256. Container bytes are allowed to differ.

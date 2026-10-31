# Authoring contract

Paraphrased from HyperFrames, <https://github.com/heygen-com/hyperframes>, commit
`95e1ac9f041ded5cd5c2a034de1dbd16c499bd04`, Apache-2.0. No upstream text is
reproduced.

## Root attributes

| Attribute | Meaning |
| --- | --- |
| `data-composition-id` | Unique id for this composition |
| `data-start` | Start offset; the root's value is `0` |
| `data-width` | Frame width in pixels |
| `data-height` | Frame height in pixels |
| `data-duration` | Rendered length in seconds |
| `data-no-timeline` | Declared on the root when all motion is CSS |

Omitting `data-start` on the root is the most common first-build failure and is
reported by lint as `root_composition_missing_data_start`.

## Layout

The root needs a real sized box in CSS, and every ancestor of a
percentage-height child needs a resolved height. An unsized root does not fail
loudly — it collapses the layout toward the top-left corner while the gates
still report success. Look at a rendered still before believing a green gate.

Element ids must be unique across the whole assembled page.

## Determinism rules

- Time comes only from the composition's own timeline. Never read a wall clock
  (`Date.now()`, `new Date()`, `performance.now()` as a content value).
- No unseeded randomness. No dependence on input state, viewport, or the host
  machine.
- Every animation is finite. No infinite repeat; use an explicit count.
- No network at author or render time: no CDN, no remote fonts, no fetched
  assets. Everything is local, including the font stack.
- Animate visual properties only — transform, opacity, colour, and similar.
  Do not animate `display`.
- Seeking directly to a timestamp must produce the same frame as playing to it.

## Motion sidecar

The sidecar carries the assertions the brief demands: which elements appear,
their order, that they stay in frame, that motion is live rather than static,
and the static budget. Populate `maxStaticSec` and the lead-in and final hold
allowances from the brief, before authoring, never from measurements of the
composition being certified.

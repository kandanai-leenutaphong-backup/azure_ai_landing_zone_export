# HyperFrames Motion

A composition is an ordinary HTML file that a headless browser renders frame by
frame. Every frame must be a pure function of its timestamp. That single
property is what the rest of this contract protects.

## Portable Runtime

`@agentcraft/hyperframes-tools` owns the [runner](scripts/hf.mjs), typed APIs and local fixture.
Set `LIBRARY_ROOT` to its canonical or installed package directory. Follow [README.md](README.md)
to install the separately pinned upstream runtime, then supply absolute `WORK_ROOT` and
`RUNTIME_ROOT` on every native invocation:

```bash
"$RUNTIME_ROOT/node_modules/node/bin/node" "$LIBRARY_ROOT/scripts/hf.mjs" \
  --root "$WORK_ROOT" --runtime "$RUNTIME_ROOT" -- lint compositions/example --json
```

Project/output arguments after `--` are relative to `WORK_ROOT`, not the library or original project.
Rendering needs `--allow-render` before `--`; browser setup needs `--allow-browser-install`.
No MCP server or cloud renderer is installed. Read [GOTCHAS.md](GOTCHAS.md), including the unresolved
moderate upstream archive dependency advisory, before using untrusted material.

Full details live one level deep:

- [`references/authoring-contract.md`](references/authoring-contract.md) — root
  attributes, layout rules, determinism rules.
- [`references/gates-and-evidence.md`](references/gates-and-evidence.md) — gate
  order, sampling, evidence layout, the network sweep.
- [`references/critique-rubric.md`](references/critique-rubric.md) — what to
  look for when reviewing snapshots by eye.

## Non-negotiables

The root element sits directly in the body and carries `data-composition-id`,
`data-start="0"`, `data-width`, `data-height` and `data-duration`, plus a real
sized box in CSS. A missing `data-start` is reported by lint as
`root_composition_missing_data_start`; an unsized root fails silently while
gates stay green.

Motion here is finite CSS animation and no animation library is loaded. A
CSS-only composition declares `data-no-timeline` on the root on the **first**
authoring pass, not after a gate complains.

Time comes only from the composition's own timeline, never a wall clock. No
unseeded randomness, no input or viewport dependence, no network at author or
render time, no infinite repeat, and no animation of `display`. Seeking to a
timestamp must produce the frame that playing to it would.

## Refusals

Refuse to build, and produce no composition, when a brief requires any of:

- an **unsized root** composition,
- a **wall-clock** time source such as `Date.now()`,
- an **infinite animation** or unbounded repeat.

Name each violating constraint present in the brief, say why it breaks the
determinism contract, and stop. Do not repair a brief that has forbidden
repair, and do not build a corrected version anyway. Describing what a
compliant version would require is allowed; building it is not.

## Beats before markup

Write the beat map before authoring: composition id, duration, and each named
beat as `{startSec, endSec}`, saved as JSON in the evidence directory.

The beat map fixes two things the gates cannot supply.

**Static budget.** Take `maxStaticSec` and the acceptable lead-in and final
hold from the brief, then write them into the motion sidecar. Deriving those
limits from the composition you already built produces a threshold that
certifies its own design. Report lead-in and final hold as numbers in seconds.

**Sampling.** `--at-transitions` yields zero samples for CSS motion, so it
proves nothing about your beats. Derive a bounded CSV with at least one
timestamp strictly inside every beat and run
`check <project> --json --snapshots --at <csv>` through the bundled runner.
Timestamps are unsigned decimals, strictly increasing, at most twenty, and
inside the duration; the wrapper refuses anything else. Report any unsampled
beat; target zero.

## Choreography rules that gates cannot see

- Keep the receiving boundary of a target visible for the whole approach. The
  travelling element must not overlap the target before the explicit alignment
  beat, or docking reads as smear.
- A passing contrast audit does not certify text that is mid-opacity-ramp.
  Inspect every ramping label in a sampled frame and confirm it is readable, or
  hold it fully opaque before it matters.
- Compose for the full frame. Action confined to the centre with large empty
  margins wastes the format.

## Gate order

1. **Beat map** written to evidence.
2. **Author** the composition from the brief.
3. **Lint** — static contract check. Fix every finding.
4. **Check** with JSON, snapshots and `--at-transitions`. A zero-sample result
   is the expected CSS control, not coverage.
5. **Check** again with the explicit `--at` CSV from the beat map.
6. **Review the snapshots by eye.** This step, not the gates, catches collapsed
   layout, overlap, dead time and unreadable text.
7. **Render** — only when render approval was given.
8. **Probe** with ffprobe: codec, duration, dimensions, frame rate.
9. **Repeat render** and compare decoded frames at fixed timestamps. Container
   bytes may differ; decoded frames must not.

A failure sends you back to authoring, not forward. Every gate runs through
the bundled [runner](scripts/hf.mjs), which permits only this capability's exact command shapes and
refuses everything else before the CLI is reached. A wrapper refusal is a
finding to report, never something to route around.

## Evidence

Keep lint and check JSON from every pass, including failing ones. Copy each
check's snapshots to `snapshots-passN/` immediately, before the next check
overwrites them, and keep transition and explicit sets in separate named
directories with the beat each snapshot belongs to recorded.

Search every check stderr **and every render log** for `Google Fonts`,
`Fetched`, and `http`. A remaining fetch is reported as a named tool exception;
a clean footprint may not be claimed from a partial search.

Record attempts per gate, the defects found by eye, and the snapshot filename
backing each visual claim. A blocked gate is a result: report it plainly rather
than substituting a different tool.

## Attribution

This skill paraphrases the authoring contract of HyperFrames, from
<https://github.com/heygen-com/hyperframes> at commit
`95e1ac9f041ded5cd5c2a034de1dbd16c499bd04`, licensed Apache-2.0. No upstream
text is reproduced here. Consult the upstream skills for anything this
capability does not cover, including audio, media, sub-compositions, and cloud
rendering — all of which are out of scope here.

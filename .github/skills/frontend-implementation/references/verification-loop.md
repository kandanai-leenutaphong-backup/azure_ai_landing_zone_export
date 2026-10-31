# Technique: the frontend verification loop

Close a frontend change on measured browser evidence. Commands below are patterns: resolve paths,
scripts, browser availability and versions in the consuming project before claiming a result.

Discipline lives in [SKILL.md](../SKILL.md); this file is the runnable half.

## Surfaces

Several frontends, several stacks. They do not converge. Match the one you are in; take the surface
inventory and gate commands from the project's architecture document, not from memory.

Derive the gates from what the surface declares:

| Surface declares | Gates |
| --- | --- |
| a `package.json` with `tsc`/`typecheck` | typecheck, then `npm run build` |
| a `package.json` with no build script | the test script alone |
| no `package.json` | serve statically and drive with Playwright; there is nothing to build |

When a surface needs a Node version other than the box default, prefix `PATH` for that command
instead of switching globally, leaving other surfaces untouched.

## Loop order

Cheapest discriminating check first. Stop at the first red.

1. **Static** — typecheck. Exit code is the signal.
2. **Build** — production build. Skip only where the surface has no build step.
3. **Behavioral** — serve, then drive with Playwright.
4. **Visual** — screenshot each shipped viewport, diff, list differences, fix.

Evidence precedence: measured geometry and computed style → DOM and accessibility tree →
screenshot → network observation. DOM presence is not visibility. A screenshot can serve a frame
behind live DOM.

## Running the gates

```bash
# a surface with no build step — Playwright starts its own static server via webServer config
cd <surface>/tests && npm test

# a Vite/TypeScript surface
cd <surface>
npx tsc --noEmit
npm run build

# a surface pinned to a newer Node than the current default
cd <surface>
PATH="$NODE_BIN:$PATH" npm run build
```

Serving a static surface by hand, when driving it outside the suite:

```bash
cd <surface> && python3 -m http.server 4173 --bind 127.0.0.1
```

## Measuring instead of asserting

DOM presence proves nothing about visibility. Measure. Adapt this pattern to the surface's own test
directory, URL and selector:

```bash
cd <surface>/tests && node -e "
const { chromium } = require('@playwright/test');
(async () => {
  const b = await chromium.launch({ headless: true });
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
  await p.goto('http://127.0.0.1:4173/index.html');
  console.log(JSON.stringify(await p.evaluate(() => {
    const r = document.querySelector('#telemetry-view').getBoundingClientRect();
    return { w: r.width, h: r.height, scrollW: document.documentElement.scrollWidth };
  })));
  await p.screenshot({ path: 'screenshots/probe.png', fullPage: true });
  await b.close();
})()"
```

Rules this loop keeps proving:

- Compare `document.documentElement.scrollWidth` against `clientWidth` at every shipped viewport; a
  page that scrolls horizontally at 390px is broken even when every element is present.
- Touch targets: assert `boundingBox().height >= 44` at mobile widths, not the CSS rule.
- Status carries a text token, never colour alone.

## Browser tooling

| Need | Tool | Why |
| --- | --- | --- |
| Regression gating, acceptance suites | Playwright test runner | use the project's declared version |
| Cold-walk audit, exploratory probing | Playwright MCP | persistent state; reachable by read-only subagents |
| Perf traces, Lighthouse, source-mapped console | `chrome-devtools-mcp` | requires a configured client and compatible Chrome |
| Component sourcing | shadcn MCP | only once a surface adopts shadcn/ui |

Browser tooling is client-owned, not bundled with this skill. Check whether the client supplies
Playwright MCP or the project supplies the test runner. Use isolated browser contexts and separate
ports for concurrent work; do not overwrite a shared MCP configuration or normal browser profile.

The CLI-versus-MCP split is Microsoft's own guidance, stated identically in both readmes: CLI
invocations keep large tool schemas and verbose accessibility trees out of context, suiting
high-throughput implementation; MCP suits loops needing persistent state and iterative reasoning
over page structure. Implementation gating stays on the test runner. Auditing wants MCP.

Playwright MCP is explicitly **not** a security boundary, and neither are `--allowed-origins` /
`--blocked-origins`.

Browser binaries and required host libraries must be available. A test package being installed
does not prove its matching browser is installed. Record missing tooling as a blocker, not a pass.

## Failure signatures observed

**`tail` swallows output.** A trailing `tail` withholds stdout until EOF and the call gets
backgrounded. Stream raw or through `tee`, then filter the saved file.

**Screenshot lags the DOM.** Measure geometry for the assertion; keep the screenshot as
corroboration, never as sole evidence.

**Stale assertions outlive the feature.** Three mockup tests failed against behaviour that had
legitimately changed — a drop target moved to the connector, boxes that became movable view state,
hard-coded pixel coordinates after geometry became responsive. Assertions pinned to literal
coordinates rot; assert the invariant (positions unchanged across a selection change) instead.

**Sampling mid-drag proves nothing.** A drag-state assertion sampled halfway between source and
target saw no drop-active class. Sample at the destination.

## Recording a broken command

A command in a README that does not run is a defect, not a typo. When one is found out of scope,
record it — where it lives, its exit code, the visible root cause from its own output — and leave it
out of the gate until repaired. Fix the command or the code; never delete the command to make a
check pass. Observed examples: a lint script passing a flag the installed linter removed; a test
suite failing on an undefined auth helper rather than on the surface under change.

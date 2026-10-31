# HyperFrames Tools

Portable, bounded local rendering over HyperFrames 0.8.12. Preserves the source authoring/evidence
guidance and adds an explicit-root runner, a dependency lock, safe ZIP extraction helper, parser
tests and a reproducible two-render fixture. No origin checkout or project-specific runner needed.

Canonical owner: `.github/skills/hyperframes-motion`; npm package `@agentcraft/hyperframes-tools`.
The package exports ESM and declarations for the functions in [CONTRACT.md](CONTRACT.md), plus
the `hyperframes-tools` command. Only `parse5@7.3.0` is a core dependency; the engine is never forked
or copied into this library. No npm registry publication is claimed.

Set `LIBRARY_ROOT` to an external source copy or installed package directory. Core checks use Node 20.20+
and never invoke the native engine or browser:

Run `npm ci` only for a source copy; installed artifacts already resolve `parse5`.

```bash
npm ci --prefix "$LIBRARY_ROOT"
npm test --prefix "$LIBRARY_ROOT"
node "$LIBRARY_ROOT/examples/validate.mjs"
```

For separately authorized native use, choose two separate external directories,
`RUNTIME_ROOT` for dependencies/caches and `WORK_ROOT` for compositions/output. Keep both outside
the installed library. The manifest and lock under `runtime/` describe upstream dependencies, not
another maintained engine. Setup downloads packages/browser binaries, so run it deliberately:

```bash
mkdir -p "$RUNTIME_ROOT" "$WORK_ROOT"
cp "$LIBRARY_ROOT/runtime/package.json" "$LIBRARY_ROOT/runtime/package-lock.json" "$RUNTIME_ROOT/"
HYPERFRAMES_SKIP_SKILLS=1 HYPERFRAMES_NO_TELEMETRY=1 npm ci --prefix "$RUNTIME_ROOT"
NODE="$RUNTIME_ROOT/node_modules/node/bin/node"
python3 "$LIBRARY_ROOT/tests/selftest.py" --runtime "$RUNTIME_ROOT"
"$NODE" "$LIBRARY_ROOT/scripts/hf.mjs" --root "$WORK_ROOT" --runtime "$RUNTIME_ROOT" \
  --allow-browser-install -- browser ensure
"$NODE" "$LIBRARY_ROOT/tests/render_smoke.mjs" --root "$WORK_ROOT" --runtime "$RUNTIME_ROOT"
```

Use Node 22+ for normal operation. The lock includes a Node 22 executable; installation under an
older npm host can emit engine warnings, but the runner refuses to execute HyperFrames under it.
The setup above creates no MCP server or client instructions. The render smoke test intentionally
produces two local MP4s in a scratch work root; it must not target existing user output.

The test runs actual lint/check, verifies 640x360 at 30fps for two seconds, proves sampled frames
are nonblank and moving, and compares decoded RGB bytes across both renders. It retains logs,
sampled PNGs, media metadata and hashes under the work root's `evidence/`. These fixed-format
composition dimensions are not a responsive application UI.

For authoring, use the same command prefix followed by the allowed shapes in
[references/gates-and-evidence.md](references/gates-and-evidence.md). Read the brief and author its
beat map before markup. Use existing local assets and inspect retained frames; successful lint is
not sufficient visual proof. Runtime setup is not authorization for cloud publishing or arbitrary
upstream CLI commands.

[CONTRACT.md](CONTRACT.md) defines boundaries. [GOTCHAS.md](GOTCHAS.md) records the unresolved
upstream dependency advisory. Linux was exercised; Windows and macOS were not.

Native prerequisites: Node 22+, HyperFrames 0.8.12, FFmpeg, FFprobe, and Chromium for checks/renders;
the safe ZIP helper also needs Python 3. The historical native fixture evidence is retained guidance,
not a new render result. Native selftest/render must be reported unverified when no explicit runtime
is available. Core installation neither downloads Chromium nor approves rendering/browser setup.

## Migration Verification

2026-09-16: four wrapper/parser/approval/CLI-symlink tests, the beat-sampling public example and
declaration checking passed on Node 20.20.0. No explicit native runtime was configured and the
former skill-local Node executable was absent. `tests/selftest.py --runtime ...` and native
lint/check/render/probe/repeat-render were not run; their prerequisites and advisory remain open.

Framework scope: F2 ESM/declarations and F3 explicit roots/approvals are tested. F4 retains `Refusal`
and native status/stdout/stderr; F5 is an explicit synchronous subprocess interface; F6 retains
duration/dimension/sample/output/timeout bounds, not a shared run budget. F7 output/evidence remains
host-owned, with no automatic replay or state deletion. F8 keeps exact command shapes and upstream
engines. F1 generated descriptions and shared framework metadata remain parent-owned; native or
full-profile conformance is not inferred from parser tests.
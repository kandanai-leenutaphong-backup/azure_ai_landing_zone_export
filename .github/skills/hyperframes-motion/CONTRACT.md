# Motion Contract

`@agentcraft/hyperframes-tools` owns the authoring method and bounded CLI adapter. Upstream
HyperFrames owns browser playback, sampling and encoding. The adapter declares `parse5` directly;
native Node, HyperFrames and media binaries remain in the supplied external runtime. Importing the
library starts no process, creates no cache and performs no network access.

`configuration(root, runtime)` requires distinct existing absolute roots outside the library.
`containedPath` rejects traversal and escaping symlinks. `composition(html, parse?)` uses parse5
to require one direct-body CSS composition with declared start, dimensions and finite duration.
`parseAtTimestamps` enforces unsigned decimals, increasing order, at most twenty samples, all
strictly inside the duration. Maximum duration is eight seconds; dimensions are at most 4096.

`validate` accepts only version, doctor, lint, check, render and explicitly authorized browser
setup shapes. `runAllowed` validates before spawning HyperFrames, closes stdin and bounds runtime.
Render requires explicit approval; the runner never exposes template download, installation of
arbitrary assets, bundle/export, publication or cloud commands.

CSS-only local composition is the supported subset. Scripts, event handlers and nested browsing
contexts are refused. Referenced local assets and CSS still need review; markup checks are not an
OS sandbox or a complete CSS security parser. Use a restricted runtime for untrusted inputs.
Stored output and actual decoded frames, not CLI acknowledgement, establish render success.

Public ESM API and declarations: `configuration`, `containedPath`, `composition`,
`parseAtTimestamps`, `validate`, `runtimeFacts`, `runAllowed`, `Refusal`, `LIBRARY_ROOT`,
`MAX_DURATION_SEC`, `MAX_TIMESTAMPS`. Installed command: `hyperframes-tools`.
Validation supports Node 20.20+; native execution explicitly refuses Node below 22. The synchronous
runner has a default 600000ms timeout and 32MiB output buffer. It supplies no async cancellation,
distributed budget, render authorization or OS isolation beyond the stated adapter checks.
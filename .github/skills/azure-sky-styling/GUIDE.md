# Azure Sky Styling

The complete [design and reuse contract](README.md), scoped CSS, React gallery, plain HTML,
depth-effect recipes, local fonts/artwork notices, generation scripts and tests are included.
No live application, authentication, dataset or cloud configuration is imported.

Consume CSS under `.azure-sky`, or opt-in depth classes from the separate stylesheet. Import
the declared npm package public exports rather than copying individual rules into consumers.
Preserve existing application design unless Azure Sky is the requested theme. Demo save/export
behaviors are local synthetic fixtures; production service APIs remain host-owned.

Canonical source is `.github/skills/azure-sky-styling`; package name is `@harness/azure-sky-styling`.
Copy this skill bundle into an external working directory, run `npm ci`, `npm run build`, then the
documented verification commands. `npm pack` produces ESM, declarations, CSS, source assets and
required notices; import the package and `@harness/azure-sky-styling/styles.css` in the host.
Dependency and screenshot output must not be installed in the shared plugin directory. The gallery can be
served on a free loopback port using its existing Vite commands. All publisher notices travel
with assets; no external artwork or font service is contacted at runtime.
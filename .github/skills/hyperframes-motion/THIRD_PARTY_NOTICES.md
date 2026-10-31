# External Runtime Licenses

This skill distributes authored workflow/runner code and dependency metadata, not an installed
HyperFrames runtime or media-tool binaries. The runner requires work and runtime directories
outside the installed skill and refuses either directory inside it.

The locked runtime has licenses separate from this repository's MIT license:

| Dependency | Terms recorded in the lock or upstream reference |
| --- | --- |
| HyperFrames | Apache-2.0; see the public source reference in PROVENANCE.md |
| FFmpeg and ffprobe installer packages | Platform-dependent GPL-3.0/GPLv3 or LGPL-2.1 builds |
| Sharp/libvips platform packages | LGPL-3.0-or-later, with Apache-2.0/MIT terms for some wrappers |
| parse5 | MIT |

Installing these tools for local execution is not permission to redistribute an assembled runtime.
Do not include runtime directories, `node_modules`, binary caches or downloaded browser/tool
packages in a skill release. An operator distributing those separate artifacts must preserve
their actual licenses and satisfy any source-offer, relinking or other applicable obligations.
Changing a filename, removing a notice or citing the repository's MIT license does not satisfy
those obligations.

No runtime package is automatically relicensed here. Use the locked versions and their supplied
notices when reviewing a separate runtime distribution. Generated media also requires rights to
the input assets; this skill supplies only its authored example, not customer media.
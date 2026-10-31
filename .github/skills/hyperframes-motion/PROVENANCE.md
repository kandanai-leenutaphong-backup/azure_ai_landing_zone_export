# Provenance

This distribution contains the authored motion workflow, runner, ZIP extraction helper and local
rendering fixture. Work and runtime roots are explicit operator inputs, not private checkout
paths. No customer media, captured application output or third-party source asset is included.

The runner uses parse5, approval/path tests and pinned package resolution. Runtime packages are
installed through npm under their own licenses; their contents are not vendored here.

The source guidance paraphrases HyperFrames commit `95e1ac9f041ded5cd5c2a034de1dbd16c499bd04`
(Apache-2.0), as attributed in the retained references. Public upstream attribution is retained;
it does not authorize redistribution of arbitrary media used with the renderer.

[External runtime licenses](THIRD_PARTY_NOTICES.md) distinguish the separate GPL/LGPL media
tools from the authored workflow distributed here. Installed runtime artifacts must stay outside
the published skill tree.
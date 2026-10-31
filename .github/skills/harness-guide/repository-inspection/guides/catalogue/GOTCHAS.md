# Discovery Gotchas

- G1: An installed plugin is not the consuming repository. Resolve from the loaded skill's path;
  using the current directory can inspect the wrong project or report a false absence.
- G2: A client may never load the routing skill automatically. Explicit `harness-guide` invocation
  and the human CLI are supported fallbacks; no automatic-loading guarantee is claimed.
- G3: A keyword match is not a placement or authorization decision. Read the full selected entry.
- G4: Source-only modules are catalogued but not bundled. Their source path and prerequisites do
  not mean they are installed, runnable, or safe to fetch without permission.
- G5: A stale catalogue is an error, not an empty result. Fix its owning entry or package contents;
  never skip validation to obtain a plausible recommendation.
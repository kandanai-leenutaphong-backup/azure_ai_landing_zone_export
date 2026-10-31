# Motion Gotchas

- G1: `--at-transitions` gives no coverage for CSS-only motion. Use explicit beat timestamps.
- G2: A zero-size root can pass upstream checks. Declare dimensions and inspect the output.
- G3: Node 20 can install the lock but cannot run this HyperFrames version. Use the locked Node 22 binary.
- G4: MP4 container bytes need not match. Determinism is checked on decoded frames at fixed timestamps.
- G5: The retained upstream-runtime audit reports two moderate entries: `adm-zip` and its dependent `hyperframes`, under
  [GHSA-vwc7-r8mq-g2x9](https://github.com/advisories/GHSA-vwc7-r8mq-g2x9). No fixed version was
  offered in that retained audit. This applies to the optional `runtime/` dependency set, not the
  parser-only adapter install; no current advisory feed was queried during library migration.
  The native runtime is not claimed audit-clean. The wrapper excludes arbitrary ZIP,
  template-download and export commands; browser setup uses the included symlink-refusing ZIP helper.
  Do not feed untrusted archives or pre-populated runtime extraction trees to the upstream CLI.
  These restrictions reduce exposure; they do not remove the vulnerable dependency.
- G6: Local markup checks are not a browser/OS sandbox. Network-free fixture renders are observed
  evidence, not a guarantee about every possible authored asset or upstream dependency.
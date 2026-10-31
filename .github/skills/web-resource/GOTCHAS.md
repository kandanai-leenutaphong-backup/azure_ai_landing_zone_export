# Acquisition Gotchas

- G1: Checking only the first URL misses private redirects. Every redirect is validated, and
  connections resolve/pin addresses at connect time to prevent a second DNS lookup changing target.
- G2: A `403` is a refusal, not a reason to change methods or try a credentialed browser.
- G3: Unavailable robots metadata now fails closed. `--ignore-robots` is an explicit operator
  exception, not a portability workaround; record the permission basis in acquisition notes.
- G4: The optional screenshot runtime is the selected Python environment's Playwright installation.
  No personal Node checkout or arbitrary newest browser under the user's home is searched.
- G5: Two pages may share a title. Page filenames include a URL hash so one cannot overwrite the
  other's provenance accidentally. Text derivatives have their own hashes and entries.
- G6: Do not run two writers against one manifest. Catalogue save is not a concurrent transaction.
- G7: Blocked resources can change appearance. Inspect the screenshot and its blocked-request count;
  an image does not prove interaction, authentication, latency or complete visual parity.
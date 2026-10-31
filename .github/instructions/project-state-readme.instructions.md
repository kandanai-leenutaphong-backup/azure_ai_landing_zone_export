---
applyTo: '**'
description: 'The root README is the live project-state document: what exists, what works, what is left.'
---

# Project-state README

Project integration: [customer-service-multi-agent](customer-service-multi-agent.instructions.md).
Keep requested, implemented, locally checked and deployed states distinct. An absent app folder
or a synthetic judge result is not evidence of a shipped app or business value.
Report the four specialized judges and calibration status from evidence. Absent qualifying
human labels and measured agreement means `uncalibrated`, regardless of a working UI or batch.

**The consuming project's root `README.md` answers one question: what exists, what works, what is left.**

Update it in the same change that makes it wrong — a component added or removed, a contract or
entry point changed, a feature landing or abandoned, a limitation opening or closing. Leave it
alone for refactors, invisible fixes, and documentation edits elsewhere.

- Summary, not manual. Roughly 150 lines is the ceiling; detail belongs to the authority that owns
  it, linked rather than restated.
- Every factual claim is read from source or a run, not remembered.
- "What is left" is honest. A limitation removed because it is awkward is a defect introduced.
- No credential value; name and location only.

## Does not apply when

The README already states the outcome correctly, or the change alters nothing it states.

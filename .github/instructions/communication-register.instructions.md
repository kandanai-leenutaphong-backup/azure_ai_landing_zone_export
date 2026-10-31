---
applyTo: '**'
description: 'Register for every response: substance stays, fluff dies.'
---

# Communication register

Project context: [customer-service-multi-agent](customer-service-multi-agent.instructions.md).
Distinguish synthetic scenarios, supplied Azure targets and observed runtime evidence.
End user-facing messages with `mewpilot`; do not use em dashes in them.

**Smart caveman. Substance stays. Fluff dies.**

Binding on every agent in this repository — overseer, orchestrator, every specialist, every
module agent — in every mode of work: thinking, reasoning, planning, tool use, final response.
Not a response-formatting rule with a private exemption for deliberation.

## Rules

- Answer first. Result, decision, or number in the opening line; supporting detail after.
- Drop articles, filler, pleasantries, hedging, self-narration. Fragments are fine.
- Preserve exact technical terms, identifiers, paths, commands, flags, code verbatim.
  Compression never rewrites a symbol, a hook name, or a decision word.
- Default sentence pattern: `[thing] [action] [reason]. [next step].`
- Dense bullets over prose paragraphs. One fact per bullet.
- No emoji. No restating the request. No "I will now" preamble, no "Let me know if" postamble.
- Depth matches complexity. One-line question, one-line answer; multi-file change, full evidence
  list. Brevity is not truncation of required evidence.
- Findings are `path + line + fact`, linked, never "there seems to be an issue somewhere".
- Label unproven claims inline: `assumes:` for a working premise, `unknown:` for something not
  observed. Never present either as fact.
- Register is clinical reference manual: flat, declarative, non-performative. Not rude, not
  chatty.
- When opinion is requested, give it and name the axis it optimizes (correctness, latency,
  reviewability, blast radius, cost).
- Completion is one line: what changed, what is next.

## Pace

- Optimize for rapid scoped completion at correct output. Speed never licenses skipping a check
  that would change the answer.
- Bound deliberation to the uncertainty actually present. Act once local evidence suffices; stop
  re-reading what is known.
- Narrow checks over sweeps. No unrequested adjacent fixes, no speculative abstraction.
- No fixed team, agent, or step minimum. Scope decides the shape.
- Default final answer roughly 150 words. Longer only when the user asks for depth or safety or
  correctness needs it.

## Measurement

Numbers reported are measured, never estimated. A measurement not taken is reported as `unknown`.
The imported `oplog.py` recorder is absent here. Do not run
`python3 .github/tools/oplog.py record <phase> --seconds N` or claim a timing receipt.
Use actual tool timing when available; otherwise report duration as unknown.

## Honest limitation

Nothing inspects model output or hidden reasoning. This register is a standing instruction, not an
enforced constraint.
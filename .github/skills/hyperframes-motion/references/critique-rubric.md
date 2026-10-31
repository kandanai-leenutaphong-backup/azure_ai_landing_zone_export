# Critique rubric

Automated gates were green on every pass of the first run while every
brief-level visual defect survived. Snapshot review is load-bearing. Work
through this list against retained frames, and cite the frame filename for each
answer.

## Time

- What is the lead-in, in seconds, before the first visible motion?
- What is the final hold after the last motion?
- Do any two sampled frames look identical? If so, that span is dead time.
- Do lead-in, hold and dead time fit the budget the brief set?

## Space

- Does the action use the full frame, or sit in the middle third with empty
  margins?
- Is anything clipped, overflowing, or outside the frame at any sampled time?

## Choreography

- Is the receiving boundary of the target visible throughout the approach?
- Does the travelling element overlap the target before the alignment beat? It
  should not.
- Is the decisive beat — the alignment or lock — actually captured in a
  retained snapshot?

## Legibility

- Is every label readable in the frames where it carries meaning, including
  while its opacity is ramping? A passing contrast audit does not settle this.
- Are supporting labels emphasised enough to be read at all?

## Honesty

- Does every visual claim in the report cite a retained frame?
- Does any artifact in the evidence directory contradict a claim in the report?
- Is the network sweep quoted from every log, or only from one?

Fix what this rubric finds before rendering. A defect found here costs one
authoring pass; the same defect found after render costs the render too.

# Frozen synthetic customer issues, v1

[`synthetic-customer-issues.jsonl`](synthetic-customer-issues.jsonl) contains
**20 actual LLM-generated interactions**, five variations for each implemented
journey: return, billing, shipping, policy exception. The existing private
West US 3 regional Standard model generated opening requests, two or three
anticipated follow-ups and communication behavior. The application fixture
owner supplied policy, actions, amounts and expected state deterministically.
No real customer interactions were used.

The four-level taxonomy records interaction category, complexity, persona and
adversarial condition; customer tier is additional metadata. This is a bounded
stratified sample, not a claim to cover the example's 400-case Cartesian product.
Product search, order placement and account management are not implemented.
The evaluator currently executes the opening request; anticipated follow-ups
are test context, not a claim of multi-turn memory coverage. Persona/tier
wording never overrides the service's trusted fixture tier or policy.

## Ground truth

- Binary checks require the exact authoritative tool action and a read-back
  synthetic ledger. The duplicate-charge case records only SGD 49.
- Goal-achievement anchors allocate 3 points to information accuracy, 4 to
  action correctness and 3 to customer effort. Equivalent natural language is
  accepted; action, amount and safety boundaries are exact.
- Out-of-policy completion means correct support escalation, **not** approval
  of the customer's requested return or refund. It is not customer satisfaction.
- Each row pins its fixture and content. The manifest pins dataset bytes,
  policy/catalog, deployed agent versions and generation prompt/model metadata.
- All language passed structural and contact/payment-pattern checks and was
  reviewed against the four fixture policies by the coding assistant.
  **No human expert review or judge calibration is claimed.**

Validate without model calls:

```bash
bash deploy/deploy.sh -e sea validate-dataset
```

Regeneration is billable and deliberately refuses to overwrite the frozen
cohort. Create a reviewed new version when policy, catalogue or capability
changes. Review at least quarterly, with the next date in `manifest.json`;
validation fails on policy/catalog drift or an overdue review. A changed
model/prompt also requires evaluation and provenance review.

## Regression composition

[`suites.json`](suites.json) selects four simple canaries, the full 20-case
cohort, and four contradictory-information safeguards. Safeguards are
**authored probes**, not invented historical bug fixes. Actual previously fixed
failures must carry an observed evidence reference and hash before being
classified as historical failures.

Canaries run first. A failure stops expensive evaluation. Full and safeguards
follow only after passing. Shared regional quota requires bounded sequential
calls rather than unconstrained parallel inference. The initial dataset is
not a gold baseline: genuine 50-100 human-labeled calibration examples and
explicit accepted baseline evidence are still absent. Never create passing
gold values from the Learn example or from synthetic labels.

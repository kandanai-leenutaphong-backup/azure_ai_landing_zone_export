# Synthetic Example Ledger

Every file in this directory is hand-authored illustration of record *shape*. Nothing here was
produced by a run, a model or a measurement. The numbers are invented and must never be cited as
performance, compared against real campaigns, or copied into a results table.

| File | Illustrates |
| --- | --- |
| `campaign-summary.json` | The aggregate summary shape a finished campaign writes |
| `trajectory.csv` | Per-version training/evaluation columns the trajectory chart reads |
| `versions/*.json` | Immutable generation records: hypothesis, levers, probe receipt reference |
| `detectors/1.json` | A schema-2 detector configuration with one bounded query test |
| `tools/*` | A generated evidence tool as source plus its metadata record |

Real ledgers additionally hold probe receipts, process receipts, run files and replay exemplars
written by the service. Those are host-owned outputs and are not shipped as examples.

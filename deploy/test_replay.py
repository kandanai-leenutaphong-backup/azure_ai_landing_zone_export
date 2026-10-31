"""Offline: replay row parsing, tree order and ID validation."""
import unittest
from unittest.mock import patch

import replay


def span(op, sid, parent, step=None):
    return {"timestamp": "t", "trace_id": "a" * 32, "span_id": sid, "parent_span_id": parent,
            "service": "s", "operation": op, "duration_ms": 1, "agent_step": step}


class ReplayTests(unittest.TestCase):
    def test_rows_accepts_both_query_shapes(self):
        insights = {"tables": [{"columns": [{"name": "span_id"}, {"name": "d"}],
                                "rows": [["s1", '{"agent_step": "2", "agent_id": "triage"}']]}]}
        workspace = [{"TableName": "PrimaryResult", "span_id": "s1",
                      "d": {"agent_step": 2, "agent_id": "triage"}}]
        for result in (insights, workspace):
            row = replay.rows(result)[0]
            self.assertEqual((row["span_id"], row["agent_step"], row["agent_id"]), ("s1", 2, "triage"))
            self.assertNotIn("TableName", row)

    def test_tree_orders_steps_and_roots_unknown_gateway_parent(self):
        found = [span("chat.agent", "c2", "w", 2), span("chat.agent", "c1", "w", 1),
                 span("chat.workflow", "w", "gateway"), span("chat.turn", "t", None)]
        self.assertEqual([(d, s["span_id"]) for d, s in replay.tree(found)],
                         [(0, "t"), (0, "w"), (1, "c1"), (1, "c2")])

    def test_ids_validated_before_query(self):
        for argv in (["--trace-id", 'x" or 1==1'], ["--span-id", "abc"], ["--trace-id", "a" * 31]):
            with self.assertRaises(SystemExit):
                replay.main(argv)
        with self.assertRaises(SystemExit):
            replay.conversation({}, "resp/../../admin")

    def test_cosmos_unreachable_keeps_spans_and_notes_vpn(self):
        found = [span("chat.agent", "c1", "w", 1)]
        c = {"FOUNDRY_COSMOS_ACCOUNT": "acct", "FOUNDRY_COSMOS_CONTAINER": "ct"}
        with patch.object(replay, "spans", return_value=(found, "application_insights")), \
                patch.object(replay, "agent_steps", side_effect=ConnectionError("private")):
            result = replay.replay(c, trace_id="a" * 32)
        self.assertEqual(result["agents"], [])
        self.assertIn("VPN", result["agents_note"])
        self.assertEqual(len(result["spans"]), 1)


if __name__ == "__main__":
    unittest.main()

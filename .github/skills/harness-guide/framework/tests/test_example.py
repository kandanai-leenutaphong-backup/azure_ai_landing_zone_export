import json
import socket
import subprocess
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx

from agentcraft.examples import offline_workflow
from azdata import HttpResponse
from llm_interface import LlmError
from situation_detector import RuleExecutionError


class ExampleTests(unittest.IsolatedAsyncioTestCase):
    async def test_handoffs_refusals_recovery_and_owned_cleanup_are_repeatable(self):
        original_connect = socket.socket.connect
        first = await offline_workflow()
        self.assertEqual(first, await offline_workflow())
        self.assertIs(socket.socket.connect, original_connect)
        self.assertTrue(first["synthetic"])
        self.assertEqual(first["requests"], {"data": 2, "model": 1})
        self.assertEqual([rule["id"] for rule in first["rules"]], ["all_readings", "high_readings"])
        self.assertEqual([rule["matched_sequences"] for rule in first["rules"]], [[1, 2], [2]])
        self.assertEqual(first["model"]["summary"]["matched_counts"], [2, 1])
        self.assertEqual(first["model"]["status"], "completed")
        self.assertTrue(first["model"]["run_id_shared"])
        self.assertEqual(first["budget"]["reserved"], {"data_calls": 2, "model_calls": 1, "store_calls": 5})
        self.assertEqual(first["budget"]["unknown"], {"data_calls": 0, "model_calls": 0, "store_calls": 2})
        self.assertEqual(first["refusals"]["data_grant"], "operation_not_granted")
        self.assertEqual(first["refusals"]["data_budget"], "budget_exhausted")
        self.assertEqual(first["refusals"]["model_grant"]["code"], "model_calls_denied")
        self.assertEqual(first["refusals"]["model_budget"]["code"], "budget_exhausted")
        self.assertEqual(first["refusals"]["model_budget"]["field"], "model_calls")
        self.assertEqual(first["refusals"]["pending_overwrite"], "ArtifactExists")
        self.assertEqual(first["recovery"], {
            "initial": "unknown", "recovered": "saved", "repeated": "saved",
            "verified": True, "destination_writes": 1, "pending": 0,
        })
        self.assertEqual(first["closed"], {
            "framework": True, "data": "connector_closed", "model": True,
            "identity": 1, "http": 1, "model_http": 1,
        })
        self.assertTrue(first["temporary_files_removed"])

    async def test_changed_native_rows_reach_rules_model_and_verified_save(self):
        def changed_rows(status, body):
            body[0]["Rows"] = [[8, 0], [9, 8]]
            return HttpResponse(status, body)

        with patch("agentcraft.examples.HttpResponse", side_effect=changed_rows):
            result = await offline_workflow()
        self.assertEqual(result["rules"][0]["rows"], [{"sequence": 8, "value": 0}, {"sequence": 9, "value": 8}])
        self.assertEqual([rule["matched_sequences"] for rule in result["rules"]], [[9], [9]])
        self.assertEqual(result["model"]["summary"]["matched_counts"], [1, 1])
        self.assertTrue(result["recovery"]["verified"])

    async def test_partial_native_query_is_a_rule_failure(self):
        def partial_rows(status, body):
            body[-1]["HasErrors"] = True
            return HttpResponse(status, body)

        with patch("agentcraft.examples.HttpResponse", side_effect=partial_rows), \
                patch.object(httpx.MockTransport, "handle_async_request") as model_http:
            with self.assertRaises(RuleExecutionError) as raised:
                await offline_workflow()
        self.assertEqual(raised.exception.code, "callback_failed")
        self.assertEqual(raised.exception.stage, "execute")
        self.assertEqual(raised.exception.rule_set_id, "readings")
        model_http.assert_not_called()

    async def test_incomplete_native_model_output_is_not_saved(self):
        original_http = httpx.MockTransport.handle_async_request
        artifacts = []

        async def incomplete_response(transport, request):
            response = await original_http(transport, request)
            body = response.json()
            body["status"] = "incomplete"
            body["incomplete_details"] = {"reason": "max_output_tokens"}
            return httpx.Response(200, json=body)

        @contextmanager
        def observed_directory(**options):
            with TemporaryDirectory(**options) as directory:
                try:
                    yield directory
                finally:
                    artifacts.extend(Path(directory).rglob("*.artifact.json"))

        with patch.object(httpx.MockTransport, "handle_async_request", new=incomplete_response), \
                patch("agentcraft.examples.TemporaryDirectory", new=observed_directory):
            with self.assertRaises(LlmError) as raised:
                await offline_workflow()
        self.assertEqual(raised.exception.code, "summary_not_completed")
        self.assertEqual(raised.exception.category, "interrupted")
        self.assertEqual(artifacts, [])

    def test_installed_module_runs_outside_checkout(self):
        with TemporaryDirectory(prefix="agentcraft-example-consumer-") as directory:
            completed = subprocess.run(
                [sys.executable, "-I", "-B", "-m", "agentcraft.examples"],
                cwd=directory, check=True, capture_output=True, text=True, timeout=60,
            )
        result = json.loads(completed.stdout)
        self.assertTrue(result["synthetic"])
        self.assertEqual(result["requests"], {"data": 2, "model": 1})
        self.assertTrue(result["recovery"]["verified"])
        self.assertTrue(result["temporary_files_removed"])


if __name__ == "__main__":
    unittest.main()
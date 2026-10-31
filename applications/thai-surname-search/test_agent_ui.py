import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from streamlit.testing.v1 import AppTest

from foundry_agent import AgentConnectionProbe, AgentReply, AgentTimings


def agent_ui():
    from app import render_agent_section
    render_agent_section()


def reply():
    return AgentReply(
        "Ready [source]", ("file_source",), "resp_test",
        AgentTimings(3000, 500, 2000), "gpt-4.1-mini", 50, 10, 0, 0, 256, 4096,
    )


class AgentUITests(unittest.TestCase):
    def setUp(self):
        env = {
            "AZURE_AGENT_PROJECT_ENDPOINT": "https://west.services.ai.azure.com/api/projects/project",
            "AZURE_AGENT_NAME": "regional-latency-agent",
            "AZURE_AGENT_VERSION": "1", "AZURE_AGENT_MODEL_SKU": "Standard",
            "AZURE_SEA_AGENT_PROJECT_ENDPOINT": "https://sea.services.ai.azure.com/api/projects/project",
            "AZURE_SEA_AGENT_NAME": "regional-latency-agent",
            "AZURE_SEA_AGENT_VERSION": "1", "AZURE_SEA_AGENT_MODEL_SKU": "GlobalStandard",
            "AZURE_GLOBAL_AGENT_PROJECT_ENDPOINT": "https://west.services.ai.azure.com/api/projects/project",
            "AZURE_GLOBAL_AGENT_NAME": "sku-global-latency-agent",
            "AZURE_GLOBAL_AGENT_VERSION": "1", "AZURE_GLOBAL_AGENT_MODEL_SKU": "GlobalStandard",
            "AZURE_SEA_STANDARD_AGENT_PROJECT_ENDPOINT": "",
            "AZURE_SEA_STANDARD_AGENT_NAME": "", "AZURE_SEA_STANDARD_AGENT_VERSION": "",
            "AZURE_SEA_STANDARD_AGENT_MODEL_SKU": "",
        }
        self.client = MagicMock()
        self.client.conversations.create.side_effect = [
            SimpleNamespace(id=f"conv_{index}") for index in range(30)
        ]
        patches = [
            patch.dict(os.environ, env),
            patch("app.regional_agent_client", return_value=self.client),
            patch("app.verified_agent_pair", return_value={
                "model": "gpt-4.1-mini", "version": "2025-04-14", "capacity": 10,
                "sku": "GlobalStandard", "verified_at": "2026-10-15",
            }),
            patch("app.invoke_agent", return_value=reply()),
            patch("app.time", SimpleNamespace(perf_counter=MagicMock(
                side_effect=[index * 3 for index in range(200)]
            ))),
        ]
        self.mocks = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        self.invoke = self.mocks[3]

    def send(self, at, paired=False):
        at.text_area[0].set_value("Same benchmark prompt")
        label = "Compare both regions (fresh conversations)" if paired else "Send to selected agent"
        next(button for button in at.button if button.label == label).click()
        at.run()
        self.assertFalse(at.exception)

    def test_only_requested_modes_and_model_only_default(self):
        at = AppTest.from_function(agent_ui).run()
        self.assertFalse(at.exception)
        self.assertEqual(at.selectbox[0].value, "global")
        self.assertEqual(
            at.selectbox[0].options,
            ["Global Standard: West US 3 vs SEA", "Standard: SEA vs West US 3"],
        )
        self.assertFalse(at.checkbox[0].value)
        self.assertTrue(any(button.label.startswith("Download editable flow") for button in at.get("download_button")))
        self.invoke.assert_not_called()

    def test_paired_calls_match_sku_prompt_and_alternate_regions(self):
        at = AppTest.from_function(agent_ui).run()
        self.send(at, True)
        self.send(at, True)
        calls = self.invoke.call_args_list
        self.assertEqual([call.args[1].region for call in calls], ["westus3", "sea", "sea", "westus3"])
        self.assertEqual([call.args[1].model_sku for call in calls], ["GlobalStandard"] * 4)
        self.assertEqual(len({call.args[1].project_endpoint for call in calls}), 2)
        self.assertTrue(all(call.kwargs["tool_choice"] == "none" for call in calls))
        self.assertTrue(all(call.args[3] == "Same benchmark prompt" for call in calls))
        self.assertEqual([call.args[2] for call in calls], [f"conv_{index}" for index in range(4)])
        rows = at.session_state["regional_agent_measurements"]
        self.assertTrue(all(row["comparison_complete"] and row["comparison_mode"] == "global" for row in rows))
        self.assertEqual(rows[0]["request_payload_bytes"], 256)
        self.assertEqual(at.dataframe[-2].value["samples"].tolist(), [2, 2])
        self.assertTrue(any("Last complete" in caption.value for caption in at.caption))

    def test_standard_sea_is_explicitly_blocked_without_any_model_call(self):
        at = AppTest.from_function(agent_ui).run()
        at.selectbox[0].set_value("standard").run()
        self.assertFalse(at.exception)
        self.assertTrue(any("Standard SEA vs Standard West US 3 is unavailable" in error.value for error in at.error))
        self.assertEqual(len(at.text_area), 0)
        self.assertTrue(next(button for button in at.button if button.label.startswith("Compare both")).disabled)
        self.assertTrue(any("hypothetical" in warning.value.lower() for warning in at.warning))
        self.invoke.assert_not_called()

    def test_failed_live_verification_blocks_comparison_instead_of_relabeling(self):
        self.mocks[2].side_effect = ValueError("actual deployment is not GlobalStandard")
        at = AppTest.from_function(agent_ui).run()
        self.assertFalse(at.exception)
        self.assertTrue(any("actual deployment" in error.value for error in at.error))
        self.assertEqual(len(at.text_area), 0)
        self.invoke.assert_not_called()

    def test_chat_context_reused_but_regions_and_workloads_are_separate(self):
        at = AppTest.from_function(agent_ui).run()
        for region, search in (("westus3_global", False), ("sea", False), ("westus3_global", False), ("westus3_global", True)):
            at.radio[0].set_value(region)
            at.checkbox[0].set_value(search)
            at.run()
            self.send(at)
        self.assertEqual([call.args[2] for call in self.invoke.call_args_list], ["conv_0", "conv_1", "conv_0", "conv_2"])
        self.assertEqual([call.kwargs["tool_choice"] for call in self.invoke.call_args_list], ["none", "none", "none", "auto"])
        self.assertTrue(any("file_source" in caption.value for caption in at.caption))

    def test_primary_and_full_timings_survive_rerun_and_add_up(self):
        at = AppTest.from_function(agent_ui).run()
        self.send(at)
        at.run()
        values = {metric.label: metric.value for metric in at.metric}
        self.assertEqual(values["Responses API time"], "3.00 s")
        self.assertEqual(values["Responses API first text"], "0.50 s")
        self.assertEqual(values["SEA app response time"], "6.00 s")
        self.assertEqual(values["SEA app time to first token"], "3.50 s")
        self.assertEqual(values["Foundry server reference (overlapping)"], "2 s")
        row = at.session_state["regional_agent_measurements"][0]
        self.assertEqual(row["client_conversation_setup_ms"], 3000)
        self.assertEqual(row["app_response_ms"], 6000)
        self.assertEqual(row["app_first_token_ms"], 3500)
        self.assertIn("Ready [source]", [message.value for message in at.markdown])

    def test_new_conversation_keeps_measurements_and_clear_keeps_diagram(self):
        at = AppTest.from_function(agent_ui).run()
        self.send(at)
        next(button for button in at.button if button.label == "New agent conversation").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.metric), 0)
        self.assertEqual(len(at.session_state["regional_agent_measurements"]), 1)
        next(button for button in at.button if button.label == "Clear captured latency measurements").click().run()
        self.assertEqual(len(at.session_state["regional_agent_measurements"]), 0)
        self.assertEqual(len(at.get("download_button")), 1)
        self.client.agents.delete.assert_not_called()

    def test_partial_and_warmup_pairs_do_not_enter_medians_or_flow(self):
        self.invoke.side_effect = [reply(), reply(), RuntimeError("denied"), reply()]
        at = AppTest.from_function(agent_ui).run()
        for warmup in (True, False):
            at.checkbox[1].set_value(warmup).run()
            self.send(at, True)
        rows = at.session_state["regional_agent_measurements"]
        self.assertEqual([row["comparison_complete"] for row in rows], [True, True, False])
        self.assertEqual([row["warmup"] for row in rows], [True, True, False])
        self.assertFalse(any("samples" in frame.value.columns for frame in at.dataframe))
        self.assertTrue(any("No complete measured pair" in caption.value for caption in at.caption))
        self.assertTrue(any("denied" in error.value for error in at.error))

    def test_sessions_do_not_share_conversations(self):
        first, second = [AppTest.from_function(agent_ui).run() for _ in range(2)]
        self.send(first)
        self.send(second)
        self.assertEqual([call.args[2] for call in self.invoke.call_args_list], ["conv_0", "conv_1"])

    def test_probe_does_not_invoke_model_and_failed_probe_clears_stale_result(self):
        probe = AgentConnectionProbe("west.services.ai.azure.com", "10.80.6.10", "now", 5, (200,) * 5)
        with patch("app.measure_agent_connection", side_effect=[probe, OSError("blocked")]) as measure:
            at = AppTest.from_function(agent_ui).run()
            for expected in ("200.0 ms", None):
                next(button for button in at.button if button.label == "Measure connection latency").click().run()
                self.assertFalse(at.exception)
                self.assertEqual(at.metric[0].value if at.metric else None, expected)
            self.assertEqual(measure.call_count, 2)
            self.assertTrue(any("measurement failed: blocked" in error.value for error in at.error))
            self.invoke.assert_not_called()

    def test_empty_prompt_is_visible_error_without_model_call(self):
        at = AppTest.from_function(agent_ui).run()
        next(button for button in at.button if button.label.startswith("Compare both")).click().run()
        self.assertTrue(any("Enter a message" in error.value for error in at.error))
        self.invoke.assert_not_called()

    def test_assumed_monthly_volume_is_applied_once_in_each_direction(self):
        at = AppTest.from_function(agent_ui).run()
        next(field for field in at.number_input if field.label == "Assumed request KiB per call").set_value(1024.0)
        next(field for field in at.number_input if field.label == "Assumed response KiB per call").set_value(1024.0)
        next(field for field in at.number_input if field.label == "Calls per regional endpoint / month").set_value(1000)
        at.run()
        cost = next(frame.value for frame in at.dataframe if "Estimated USD" in frame.value.columns)
        self.assertAlmostEqual(cost.iloc[0]["Estimated USD"], 2 * 1024**2 * 1000 / 1e9 * 0.01)
        self.assertAlmostEqual(cost.iloc[1]["Estimated USD"], 2 * 1024**2 * 1000 / 1e9 * 0.135)

    def test_native_iframe_is_preferred_without_dropping_older_streamlit_support(self):
        import app
        with patch.object(app.st, "iframe", create=True) as native, patch("app.components.html") as legacy:
            app.render_agent_html("<p>Trusted generated diagram</p>", 100)
            native.assert_called_once_with(
                "<p>Trusted generated diagram</p>", height=100,
                alt="Foundry regional flow and timing visualization",
            )
            legacy.assert_not_called()


if __name__ == "__main__":
    unittest.main()

import os
import hashlib
import socket
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from openai.types.responses import Response, ResponseFileSearchToolCall, ResponseFunctionToolCall
from azure.ai.projects.models import FileSearchTool, ModelDeployment, ModelDeploymentSku, PromptAgentDefinition
from azure.core.exceptions import ResourceNotFoundError

from foundry_agent import (
    GLOBAL_MODEL_DEPLOYMENT, AgentSettings, invoke_agent, measure_agent_connection,
    validate_sku_comparison, verify_regional_agents,
)
from provision_agents import DOCUMENT, INSTRUCTIONS, MODEL, provision


SETTINGS = AgentSettings(
    "https://example.services.ai.azure.com/api/projects/project",
    "regional-latency-agent", "1", "westus3", "Standard",
)
ENV = {
    "AZURE_AGENT_PROJECT_ENDPOINT": SETTINGS.project_endpoint,
    "AZURE_AGENT_NAME": SETTINGS.agent_name,
    "AZURE_AGENT_VERSION": "1",
    "AZURE_AGENT_MODEL_SKU": "Standard",
}
GLOBAL_SETTINGS = replace(SETTINGS, agent_name="sku-global-latency-agent", model_sku="GlobalStandard")
GLOBAL_ENV = {
    key.replace("AZURE_AGENT", "AZURE_GLOBAL_AGENT"): value for key, value in ENV.items()
}
GLOBAL_ENV.update({
    "AZURE_GLOBAL_AGENT_NAME": GLOBAL_SETTINGS.agent_name,
    "AZURE_GLOBAL_AGENT_MODEL_SKU": "GlobalStandard",
})


class AgentSettingsTests(unittest.TestCase):
    def test_missing_configuration_is_explicit(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "Configure"):
                AgentSettings.from_env()

    def test_project_endpoint_is_validated(self):
        for endpoint in (
            "http://example.com/api/projects/project",
            "https://example.com/api/projects/project",
            "https://example.services.ai.azure.com/api/projects/",
            "https://example.services.ai.azure.com/api/projects/project?key=value",
        ):
            with self.subTest(endpoint=endpoint), patch.dict(
                os.environ, {**ENV, "AZURE_AGENT_PROJECT_ENDPOINT": endpoint}
            ):
                with self.assertRaises(ValueError):
                    AgentSettings.from_env()

    def test_valid_configuration(self):
        with patch.dict(
            os.environ,
            {
                **ENV,
                "AZURE_AGENT_PROJECT_ENDPOINT": SETTINGS.project_endpoint + "/",
            },
        ):
            self.assertEqual(
                AgentSettings.from_env().project_endpoint,
                "https://example.services.ai.azure.com/api/projects/project",
            )

    def test_classic_ids_invalid_versions_and_unknown_skus_are_rejected(self):
        for field, value in (
            ("AZURE_AGENT_NAME", "asst_test"),
            ("AZURE_AGENT_NAME", "../agent"),
            ("AZURE_AGENT_VERSION", "0"),
            ("AZURE_AGENT_VERSION", "latest"),
            ("AZURE_AGENT_MODEL_SKU", "unknown"),
        ):
            with self.subTest(field=field, value=value), patch.dict(os.environ, {**ENV, field: value}):
                with self.assertRaises(ValueError):
                    AgentSettings.from_env()

    def test_sea_configuration_is_separate(self):
        sea = {key.replace("AZURE_AGENT", "AZURE_SEA_AGENT"): value for key, value in ENV.items()}
        sea["AZURE_SEA_AGENT_MODEL_SKU"] = "GlobalStandard"
        with patch.dict(os.environ, {**ENV, **sea}):
            self.assertEqual(AgentSettings.from_env("sea").model_sku, "GlobalStandard")
            self.assertEqual(AgentSettings.from_env().model_sku, "Standard")

    def test_global_comparison_target_is_in_westus3_not_a_new_region(self):
        with patch.dict(os.environ, {**ENV, **GLOBAL_ENV}):
            self.assertEqual(AgentSettings.from_env("westus3_global"), GLOBAL_SETTINGS)
            validate_sku_comparison(AgentSettings.from_env(), AgentSettings.from_env("westus3_global"))

    def test_sku_comparison_rejects_different_projects_regions_skus_or_same_agent(self):
        for changed in (
            replace(GLOBAL_SETTINGS, project_endpoint=SETTINGS.project_endpoint + "-other"),
            replace(GLOBAL_SETTINGS, region="sea"),
            replace(GLOBAL_SETTINGS, model_sku="Standard"),
            replace(GLOBAL_SETTINGS, agent_name=SETTINGS.agent_name),
        ):
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, "same Foundry project"):
                validate_sku_comparison(SETTINGS, changed)


class AgentInvocationTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.response = Response.model_validate(
            {
                "id": "resp_test", "object": "response", "created_at": 100,
                "completed_at": 102, "status": "completed", "model": "gpt-4.1-mini",
                "error": None, "incomplete_details": None, "instructions": None,
                "metadata": {}, "parallel_tool_calls": True, "tools": [],
                "tool_choice": "auto", "temperature": 0, "top_p": 1,
                "usage": {"input_tokens": 50, "output_tokens": 10, "total_tokens": 60,
                          "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                          "output_tokens_details": {"reasoning_tokens": 0}},
                "output": [{
                    "id": "msg_test", "type": "message", "role": "assistant", "status": "completed",
                    "content": [{
                        "type": "output_text", "text": "WESTUS3-SPOKE-READY",
                        "annotations": [
                            {"type": "file_citation", "file_id": "file_test", "filename": "ready.txt", "index": 0},
                            {"type": "file_citation", "file_id": "file_test", "filename": "ready.txt", "index": 1},
                        ],
                    }],
                }],
            }
        )
        self.events = [
            SimpleNamespace(type="response.output_text.delta", delta="Ready"),
            SimpleNamespace(type="response.completed", response=self.response),
        ]
        self.stream = self.client.responses.create.return_value
        self.stream.__enter__.return_value.__iter__.return_value = self.events
        self.stream.__enter__.return_value.response = SimpleNamespace(
            request=SimpleNamespace(content=b'{"input":"readiness?"}'), num_bytes_downloaded=4096,
        )

    def test_existing_agent_is_invoked_and_citations_preserved(self):
        reply = invoke_agent(self.client, SETTINGS, "conv_test", " readiness? ")
        self.assertIn("WESTUS3-SPOKE-READY", reply.text)
        self.assertEqual(reply.file_ids, ("file_test",))
        self.assertEqual(reply.timings.service_run_ms, 2000)
        self.assertEqual(reply.input_tokens, 50)
        self.assertEqual(reply.output_tokens, 10)
        self.assertEqual(reply.request_payload_bytes, len(b'{"input":"readiness?"}'))
        self.assertEqual(reply.response_payload_bytes, 4096)
        self.client.responses.create.assert_called_once_with(
            conversation="conv_test", input="readiness?", stream=True, max_output_tokens=1000,
            timeout=90, tool_choice="auto",
            extra_body={"agent_reference": {
                "type": "agent_reference", "name": "regional-latency-agent", "version": "1",
            }},
        )
        self.client.messages.create.assert_not_called()
        self.client.runs.create.assert_not_called()
        self.client.agents.create_version.assert_not_called()
        self.client.agents.delete.assert_not_called()
        self.stream.__exit__.assert_called_once()

    def test_model_only_explicitly_disables_tools_and_reports_usage(self):
        result = invoke_agent(self.client, SETTINGS, "conv_test", "hello", tool_choice="none")
        self.assertEqual(self.client.responses.create.call_args.kwargs["tool_choice"], "none")
        self.assertEqual(result.file_search_calls, 0)
        self.assertEqual(result.cached_input_tokens, 0)

    def test_search_calls_are_counted_and_cannot_be_reported_as_model_only(self):
        self.response.output.insert(0, ResponseFileSearchToolCall(
            id="fs_test", type="file_search_call", status="completed", queries=["readiness"]
        ))
        self.assertEqual(invoke_agent(self.client, SETTINGS, "conv_test", "hello").file_search_calls, 1)
        with self.assertRaisesRegex(RuntimeError, "model-only benchmark"):
            invoke_agent(self.client, SETTINGS, "conv_test", "hello", tool_choice="none")

    def test_invalid_prompt_does_not_call_foundry(self):
        for prompt in (" ", "x" * 4001):
            with self.subTest(prompt_length=len(prompt)):
                with self.assertRaises(ValueError):
                    invoke_agent(self.client, SETTINGS, "conv_test", prompt)
        self.client.responses.create.assert_not_called()

    @patch("foundry_agent.time.perf_counter", side_effect=[0, 0.3, 1.5, 2])
    def test_time_to_first_text_delta_and_complete_stream_are_measured(self, clock):
        timings = invoke_agent(self.client, SETTINGS, "conv_test", "hello").timings
        self.assertAlmostEqual(timings.first_token_ms, 300)
        self.assertAlmostEqual(timings.response_ms, 2000)
        self.assertEqual(timings.service_run_ms, 2000)

    def test_missing_or_invalid_service_timestamps_are_not_network_estimates(self):
        for completed in (None, 99):
            with self.subTest(completed=completed):
                self.response.completed_at = completed
                reply = invoke_agent(self.client, SETTINGS, "conv_test", "hello")
                self.assertIsNone(reply.timings.service_run_ms)

    def test_failed_or_incomplete_responses_are_not_success(self):
        for status in ("failed", "incomplete"):
            with self.subTest(status=status):
                self.response.status = status
                with self.assertRaisesRegex(RuntimeError, status):
                    invoke_agent(self.client, SETTINGS, "conv_test", "hello")

    def test_client_side_tools_are_not_executed(self):
        self.response.output = [
            ResponseFunctionToolCall(
                arguments="{}", call_id="call_test", name="lookup", type="function_call"
            )
        ]
        with self.assertRaisesRegex(RuntimeError, "client-side tools"):
            invoke_agent(self.client, SETTINGS, "conv_test", "hello")

    @patch("foundry_agent.time.perf_counter", side_effect=[0, 91])
    def test_elapsed_timeout_closes_stream_without_claiming_server_cancellation(self, clock):
        with self.assertRaisesRegex(TimeoutError, "Server-side processing may continue"):
            invoke_agent(self.client, SETTINGS, "conv_test", "hello")
        self.stream.__exit__.assert_called_once()
        self.client.responses.cancel.assert_not_called()

    def test_empty_response_is_not_success(self):
        self.response.output = []
        with self.assertRaisesRegex(RuntimeError, "without a text response"):
            invoke_agent(self.client, SETTINGS, "conv_test", "hello")

    def test_truncated_stream_is_not_success(self):
        self.events.pop()
        with self.assertRaisesRegex(RuntimeError, "without a terminal response"):
            invoke_agent(self.client, SETTINGS, "conv_test", "hello")

    def test_explicit_stream_error_is_visible(self):
        self.events[:] = [SimpleNamespace(type="error", message="service unavailable")]
        with self.assertRaisesRegex(RuntimeError, "service unavailable"):
            invoke_agent(self.client, SETTINGS, "conv_test", "hello")

    def test_no_text_delta_means_ttft_is_unavailable_not_zero(self):
        self.events.pop(0)
        reply = invoke_agent(self.client, SETTINGS, "conv_test", "hello")
        self.assertIsNone(reply.timings.first_token_ms)


class MatchedRegionalTests(unittest.TestCase):
    def setUp(self):
        self.sea = replace(
            GLOBAL_SETTINGS, region="sea", agent_name=SETTINGS.agent_name,
            project_endpoint="https://sea.services.ai.azure.com/api/projects/project",
        )
        self.projects = [MagicMock(), MagicMock()]
        for index, project in enumerate(self.projects):
            project.agents.get_version.return_value = SimpleNamespace(
                definition=PromptAgentDefinition(
                    model="global-west" if index == 0 else "global-sea",
                    instructions=INSTRUCTIONS, temperature=0,
                    tools=[FileSearchTool(vector_store_ids=[f"vs_{index}"])],
                ),
                metadata={"corpus_sha256": hashlib.sha256(DOCUMENT).hexdigest()},
            )
            project.deployments.get.return_value = ModelDeployment(
                name="model", model_name=MODEL, model_version="2025-04-14", model_publisher="OpenAI",
                capabilities={"chat_completion": "true"},
                sku=ModelDeploymentSku(name="GlobalStandard", capacity=10),
            )
        self.factory = patch("foundry_agent.AIProjectClient")
        factory = self.factory.start()
        factory.return_value.__enter__.side_effect = self.projects
        self.addCleanup(self.factory.stop)

    def test_matching_models_and_corpus_accept_different_regional_store_ids(self):
        verified = verify_regional_agents(GLOBAL_SETTINGS, self.sea, "GlobalStandard", MagicMock())
        self.assertEqual(verified["version"], "2025-04-14")
        self.assertEqual(verified["capacity"], 10)
        for project in self.projects:
            project.get_openai_client.assert_not_called()
            project.agents.create_version.assert_not_called()

    def test_environment_labels_cannot_hide_an_actual_sku_mismatch(self):
        self.projects[1].deployments.get.return_value.sku.name = "Standard"
        with self.assertRaisesRegex(ValueError, "actual deployment"):
            verify_regional_agents(GLOBAL_SETTINGS, self.sea, "GlobalStandard", MagicMock())

    def test_mixed_sku_or_same_region_pair_is_rejected_before_api_access(self):
        for other in (SETTINGS, GLOBAL_SETTINGS, replace(self.sea, model_sku="Standard")):
            with self.subTest(other=other), self.assertRaisesRegex(ValueError, "same model SKU"):
                verify_regional_agents(GLOBAL_SETTINGS, other, "GlobalStandard", MagicMock())
        self.projects[0].agents.get_version.assert_not_called()

    def test_changed_definition_model_version_or_corpus_blocks_comparison(self):
        changes = (
            lambda: setattr(self.projects[1].agents.get_version.return_value.definition, "temperature", 0.5),
            lambda: setattr(self.projects[1].deployments.get.return_value, "model_version", "other"),
            lambda: self.projects[1].agents.get_version.return_value.metadata.update(corpus_sha256="a" * 64),
        )
        for change in changes:
            with self.subTest(change=change):
                with patch("foundry_agent.AIProjectClient") as factory:
                    factory.return_value.__enter__.side_effect = self.projects
                    self.projects[1].agents.get_version.return_value.definition.temperature = 0
                    self.projects[1].deployments.get.return_value.model_version = "2025-04-14"
                    self.projects[1].agents.get_version.return_value.metadata["corpus_sha256"] = hashlib.sha256(DOCUMENT).hexdigest()
                    change()
                    with self.assertRaisesRegex(ValueError, "differ"):
                        verify_regional_agents(GLOBAL_SETTINGS, self.sea, "GlobalStandard", MagicMock())

    def test_missing_corpus_hash_is_not_treated_as_a_match(self):
        self.projects[0].agents.get_version.return_value.metadata = {}
        with self.assertRaisesRegex(ValueError, "hash is missing"):
            verify_regional_agents(GLOBAL_SETTINGS, self.sea, "GlobalStandard", MagicMock())


class AgentConnectionTests(unittest.TestCase):
    def setUp(self):
        self.settings = SETTINGS

    @patch("foundry_agent.socket.socket")
    @patch("foundry_agent.socket.getaddrinfo")
    def test_probe_measures_five_connections_without_dns_in_tcp_samples(self, resolve, sock):
        resolve.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.80.6.10", 443))]
        with patch(
            "foundry_agent.time.perf_counter",
            side_effect=[0, 0.005, 1, 1.25, 2, 2.3, 3, 3.2, 4, 4.4, 5, 5.35],
        ):
            probe = measure_agent_connection(self.settings)
        self.assertEqual(probe.resolved_ip, "10.80.6.10")
        self.assertAlmostEqual(probe.dns_ms, 5)
        self.assertAlmostEqual(probe.median_tcp_ms, 300)
        self.assertEqual(len(probe.tcp_samples_ms), 5)
        self.assertTrue(probe.measured_at.endswith("+00:00"))
        resolve.assert_called_once_with(
            "example.services.ai.azure.com", 443, type=socket.SOCK_STREAM
        )
        connection = sock.return_value.__enter__.return_value
        self.assertEqual(connection.connect.call_count, 5)
        connection.connect.assert_called_with(("10.80.6.10", 443))
        self.assertEqual(sock.return_value.__exit__.call_count, 5)

    @patch("foundry_agent.socket.socket")
    @patch("foundry_agent.socket.getaddrinfo")
    def test_failed_connection_is_explicit_and_closed(self, resolve, sock):
        resolve.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.80.6.10", 443))]
        sock.return_value.__enter__.return_value.connect.side_effect = TimeoutError("blocked")
        with self.assertRaisesRegex(TimeoutError, "blocked"):
            measure_agent_connection(self.settings)
        sock.return_value.__exit__.assert_called_once()

    @patch("foundry_agent.socket.getaddrinfo", return_value=[])
    def test_no_addresses_is_not_a_success_result(self, resolve):
        with self.assertRaisesRegex(OSError, "No addresses"):
            measure_agent_connection(self.settings)


class AgentProvisioningTests(unittest.TestCase):
    def setUp(self):
        credential = patch("provision_agents.DefaultAzureCredential")
        constructor = patch("provision_agents.AIProjectClient")
        credential.start()
        self.project = constructor.start().return_value.__enter__.return_value
        self.addCleanup(credential.stop)
        self.addCleanup(constructor.stop)
        self.existing = self.project.agents.get_version.return_value
        self.existing.definition = PromptAgentDefinition(
            model=MODEL, instructions=INSTRUCTIONS, temperature=0,
            tools=[FileSearchTool(vector_store_ids=["vs_test"])],
        )
        self.existing.metadata = {"corpus_sha256": hashlib.sha256(DOCUMENT).hexdigest()}
        self.existing.as_dict.return_value = {"name": SETTINGS.agent_name, "version": "1"}

    def test_existing_matching_agent_is_not_recreated(self):
        self.assertEqual(provision(SETTINGS), {"name": SETTINGS.agent_name, "version": "1"})
        self.project.get_openai_client.assert_not_called()
        self.project.agents.create_version.assert_not_called()

    def test_different_definition_is_not_silently_reused(self):
        self.existing.definition.temperature = 1
        with self.assertRaisesRegex(RuntimeError, "differs"):
            provision(SETTINGS)
        self.project.get_openai_client.assert_not_called()
        self.project.agents.create_version.assert_not_called()

    def test_existing_name_without_pinned_version_is_not_modified(self):
        self.project.agents.get_version.side_effect = ResourceNotFoundError("missing version")
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            provision(SETTINGS)
        self.project.get_openai_client.assert_not_called()
        self.project.agents.create_version.assert_not_called()

    def test_global_agent_copies_definition_and_shares_store_without_uploading(self):
        source = SimpleNamespace(
            definition=self.existing.definition, metadata=self.existing.metadata,
        )
        self.project.agents.get_version.side_effect = [source, ResourceNotFoundError("missing")]
        self.project.agents.get.side_effect = ResourceNotFoundError("missing")
        self.project.agents.create_version.return_value.version = "1"
        provision(GLOBAL_SETTINGS, SETTINGS)
        definition = self.project.agents.create_version.call_args.kwargs["definition"]
        self.assertEqual(definition.model, GLOBAL_MODEL_DEPLOYMENT)
        expected = source.definition.as_dict()
        expected["model"] = GLOBAL_MODEL_DEPLOYMENT
        self.assertEqual(definition.as_dict(), expected)
        self.assertEqual(definition.tools[0].vector_store_ids, ["vs_test"])
        self.assertEqual(source.definition.model, MODEL)
        self.project.get_openai_client.assert_not_called()
        self.project.agents.delete.assert_not_called()

    def test_global_agent_cannot_be_provisioned_without_matching_source(self):
        with self.assertRaisesRegex(ValueError, "matching Standard source"):
            provision(GLOBAL_SETTINGS)
        self.project.agents.create_version.assert_not_called()

    def test_global_agent_with_different_store_is_not_silently_reused(self):
        source = SimpleNamespace(
            definition=self.existing.definition, metadata=self.existing.metadata,
        )
        different = SimpleNamespace(
            definition=PromptAgentDefinition(
                model=GLOBAL_MODEL_DEPLOYMENT, instructions=INSTRUCTIONS, temperature=0,
                tools=[FileSearchTool(vector_store_ids=["vs_other"])],
            ),
            metadata=self.existing.metadata,
        )
        self.project.agents.get_version.side_effect = [source, different]
        with self.assertRaisesRegex(RuntimeError, "differs"):
            provision(GLOBAL_SETTINGS, SETTINGS)
        self.project.agents.create_version.assert_not_called()

    def test_global_agent_with_matching_definition_is_reused(self):
        source = SimpleNamespace(
            definition=self.existing.definition, metadata=self.existing.metadata,
        )
        self.existing.definition = PromptAgentDefinition(
            model=GLOBAL_MODEL_DEPLOYMENT, instructions=INSTRUCTIONS, temperature=0,
            tools=[FileSearchTool(vector_store_ids=["vs_test"])],
        )
        self.project.agents.get_version.side_effect = [source, self.existing]
        provision(GLOBAL_SETTINGS, SETTINGS)
        self.project.get_openai_client.assert_not_called()
        self.project.agents.create_version.assert_not_called()


if __name__ == "__main__":
    unittest.main()

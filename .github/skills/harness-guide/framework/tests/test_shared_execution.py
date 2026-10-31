import asyncio
import unittest
from types import SimpleNamespace

from agentcraft_core import CallerContext, ExecutionContext
from azdata.contracts import Limits as DataLimits
from azdata.sdk import CallContext
from azdata.transport import OperationFault
from llm_interface.config import Limits as ModelLimits
from llm_interface.errors import LlmError
from llm_interface.runtime import RunState


class SharedExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_attempts_and_verification_share_budget_with_child(self):
        run = ExecutionContext.create(CallerContext("fixture"),
            limits={"data_calls": 2, "model_calls": 1, "tool_calls": 1})
        with run.activate():
            data = CallContext(None, DataLimits())
            state = RunState(ModelLimits())
            data.record_attempt()
            child = run.child(limits={"data_calls": 1, "model_calls": 1, "tool_calls": 1})
            with child.activate():
                verification = CallContext(None, DataLimits())
                verification.record_attempt()
                state.model_attempt()
                state.reserve("tool_calls")
            with self.assertRaises(OperationFault):
                data.record_attempt()
            with self.assertRaises(LlmError):
                state.model_attempt()
            self.assertEqual(state.run_id, run.run_id)
        self.assertEqual(run.budget.snapshot()["reserved"],
                         {"data_calls": 2, "model_calls": 1, "tool_calls": 1})

    async def test_cancellation_retains_unknown_attempt_and_deadline(self):
        run = ExecutionContext.create(CallerContext("fixture"), limits={"data_calls": 1}, timeout_seconds=1)

        async def prepare():
            pass

        with run.activate():
            call = CallContext(SimpleNamespace(prepare=prepare, gate=asyncio.Semaphore(1)), DataLimits())

            async def cancel():
                call.record_attempt()
                raise asyncio.CancelledError()

            with self.assertRaises(asyncio.CancelledError):
                await call.invoke(cancel)
        self.assertEqual(run.budget.snapshot()["unknown"]["data_calls"], 1)
        self.assertLessEqual(call.deadline, run.deadline)
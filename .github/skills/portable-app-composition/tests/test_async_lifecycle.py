import asyncio
import unittest

from appcompose import CompositionError, Contribution, ShutdownFailed, StartupFailed, allowlist, compose, parse


def application(first, second):
    document = parse({"schemaVersion": 1, "kind": "portable.app-composition", "name": "fixture",
        "members": [{"id": "first", "capability": "fixture.first"},
                    {"id": "second", "capability": "fixture.second", "requires": ["first"]}]})
    return compose(document, resolve=allowlist({"fixture.first": lambda member: first,
                                              "fixture.second": lambda member: second}))


class AsyncLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_order_context_and_exactly_once_shutdown(self):
        events = []

        async def start():
            events.append("start-second")

        async def stop():
            events.append("stop-second")

        app = application(Contribution(startup=lambda: events.append("start-first"),
                                       shutdown=lambda: events.append("stop-first")),
                          Contribution(startup=start, shutdown=stop))
        async with app:
            self.assertEqual(app.readiness(), (True, ""))
            with self.assertRaises(CompositionError):
                await app.astartup()
            with self.assertRaises(CompositionError):
                app.shutdown()
        self.assertEqual(await app.aclose(), ())
        self.assertEqual(events, ["start-first", "start-second", "stop-second", "stop-first"])

    async def test_failure_and_cancellation_roll_back_completed_dependencies(self):
        for failure in (RuntimeError("fixture"), asyncio.CancelledError()):
            events = []

            async def refuse():
                raise failure

            app = application(Contribution(shutdown=lambda: events.append("closed")),
                              Contribution(startup=refuse))
            expected = StartupFailed if isinstance(failure, Exception) else asyncio.CancelledError
            with self.assertRaises(expected):
                await app.astartup()
            self.assertEqual(events, ["closed"])
            self.assertFalse(app.readiness()[0])

    async def test_shutdown_failure_does_not_skip_other_resources(self):
        events = []

        async def refuse():
            raise RuntimeError("private-provider-detail")

        app = application(Contribution(shutdown=lambda: events.append("closed")),
                          Contribution(shutdown=refuse))
        await app.astartup()
        with self.assertRaises(ShutdownFailed) as caught:
            await app.aclose()
        self.assertNotIn("private-provider-detail", str(caught.exception))
        self.assertEqual(events, ["closed"])
        self.assertFalse(app.availability())
        self.assertEqual(await app.aclose(), ())

    async def test_task_cancellation_during_shutdown_still_closes_dependencies(self):
        events = []
        stopping = asyncio.Event()

        async def stop():
            events.append("stop-second")
            stopping.set()
            await asyncio.Future()

        app = application(Contribution(shutdown=lambda: events.append("stop-first")),
                          Contribution(shutdown=stop))
        await app.astartup()
        task = asyncio.create_task(app.aclose())
        await asyncio.wait_for(stopping.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        self.assertEqual(events, ["stop-second", "stop-first"])
        self.assertEqual([member for member, _ in app.unsafe_state()], ["second"])
        self.assertFalse(app.availability())
        self.assertEqual(await app.aclose(), ())

    async def test_real_task_cancellation_during_startup_latches_unfinished_member(self):
        events = []
        starting = asyncio.Event()
        tasks_before = asyncio.all_tasks()

        async def start():
            starting.set()
            try:
                await asyncio.Future()
            finally:
                events.append("cancel-second")

        app = application(Contribution(shutdown=lambda: events.append("stop-first")),
                          Contribution(startup=start,
                                       shutdown=lambda: events.append("stop-second")))
        task = asyncio.create_task(app.astartup())
        await asyncio.wait_for(starting.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        self.assertTrue(task.cancelled())
        self.assertEqual(events, ["cancel-second", "stop-first"])
        self.assertEqual([member for member, _ in app.unsafe_state()], ["second"])
        self.assertFalse(app.availability())
        self.assertEqual(await app.aclose(), ())
        with self.assertRaises(CompositionError):
            await app.astartup()
        with self.assertRaises(CompositionError):
            app.startup()
        self.assertEqual(asyncio.all_tasks(), tasks_before)

    async def test_clean_failure_and_close_release_async_mode(self):
        failing = True

        def start():
            if failing:
                raise RuntimeError("fixture")

        app = application(Contribution(), Contribution(startup=start))
        with self.assertRaises(StartupFailed):
            await app.astartup()
        self.assertTrue(app.availability())
        failing = False
        self.assertEqual(app.startup(), ("first", "second"))
        with self.assertRaises(CompositionError):
            await app.aclose()
        app.shutdown()
        await app.astartup()
        await app.aclose()
        self.assertEqual(app.startup(), ("first", "second"))
        app.shutdown()

    async def test_async_transitions_refuse_reentrancy_and_dispatch_during_close(self):
        events = []

        async def hook():
            for method in (app.startup, app.shutdown):
                with self.assertRaises(CompositionError):
                    method()
            for method in (app.astartup, app.aclose):
                with self.assertRaises(CompositionError):
                    await method()
            self.assertFalse(app.readiness()[0])
            self.assertEqual(app.dispatch("GET", "/anything").status, 503)
            events.append("hook")

        app = application(Contribution(startup=hook, shutdown=hook), Contribution())
        await app.astartup()
        await app.aclose()
        self.assertEqual(events, ["hook", "hook"])


class SyncLifecycleTests(unittest.TestCase):
    def test_sync_transitions_refuse_reentrancy_and_mixed_async_calls(self):
        events = []

        def hook():
            for method in (app.startup, app.shutdown):
                with self.assertRaises(CompositionError):
                    method()
            for method in (app.astartup, app.aclose):
                with self.assertRaises(CompositionError):
                    asyncio.run(method())
            self.assertFalse(app.readiness()[0])
            self.assertEqual(app.dispatch("GET", "/anything").status, 503)
            events.append("hook")

        app = application(Contribution(startup=hook, shutdown=hook), Contribution())
        app.startup()
        app.shutdown()
        self.assertEqual(events, ["hook", "hook"])
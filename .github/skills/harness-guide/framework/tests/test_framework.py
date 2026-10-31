import unittest
import json
from contextlib import redirect_stderr, redirect_stdout
from importlib.metadata import distribution
from io import StringIO

from agentcraft import Binding, Framework, FrameworkError


class Resource:
    def __init__(self, name, events):
        self.name, self.events = name, events

    async def read(self):
        return {"value": 7}

    async def aclose(self):
        self.events.append(self.name)


class FrameworkTests(unittest.IsolatedAsyncioTestCase):
    def test_declared_console_entrypoint_loads(self):
        entrypoint = next(entry for entry in distribution("agentcraft").entry_points
                          if entry.group == "console_scripts" and entry.name == "agentcraft")
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(entrypoint.load()([]), 0)
        self.assertIn("usage: agentcraft", output.getvalue())

    def test_cli_description_and_unknown_capability(self):
        from agentcraft.cli import main

        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["describe", "framework"]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["capabilities"][0]["id"], "framework")
        self.assertEqual(result["readiness"], "unverified")
        with redirect_stderr(StringIO()):
            self.assertEqual(main(["describe", "not-a-capability"]), 2)
            with self.assertRaises(SystemExit) as refusal:
                main(["mcp"])
        self.assertEqual(refusal.exception.code, 2)

    async def test_explicit_bindings_offline_description_and_reverse_owned_close(self):
        events = []
        data, model, borrowed = (Resource(name, events) for name in ("data", "model", "borrowed"))
        app = Framework({"data": Binding("data.query", data, owned=True),
                         "model": Binding("model.chat", model, owned=True, requires=("data",)),
                         "view": Binding("view.text", borrowed),
                         "alias": Binding("data.query", data, owned=True)})
        self.assertEqual(events, [])
        self.assertEqual(app.describe()["readiness"], "unverified")
        async with app:
            self.assertEqual(await app.get("data", Resource).read(), {"value": 7})
            with self.assertRaises(FrameworkError):
                app.get("missing", Resource)
            with self.assertRaises(FrameworkError):
                app.get("data", str)
        await app.aclose()
        self.assertEqual(events, ["model", "data"])
        with self.assertRaises(FrameworkError):
            app.get("data", Resource)

    async def test_unknown_dependency_and_cycles_refuse_before_lifecycle(self):
        events = []
        value = Resource("one", events)
        for bindings in ({"one": Binding("fixture.read", value, requires=("missing",))},
                         {"one": Binding("fixture.read", value, requires=("two",)),
                          "two": Binding("fixture.read", value, requires=("one",))}):
            with self.assertRaises(ValueError):
                Framework(bindings)
        self.assertEqual(events, [])
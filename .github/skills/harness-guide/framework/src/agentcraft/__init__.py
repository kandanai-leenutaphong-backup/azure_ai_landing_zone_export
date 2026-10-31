"""Typed capability access; appcompose owns lifecycle and explicit binding validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeVar

from appcompose import Contribution, allowlist, compose, parse
from agentcraft_core import CallerContext, ExecutionBudget, ExecutionContext, FailureInfo, FrameworkError

__version__ = "0.1.0"
Value = TypeVar("Value")


@dataclass(frozen=True, slots=True)
class Binding:
    capability: str
    value: Any
    owned: bool = False
    requires: tuple[str, ...] = ()


class Framework:
    def __init__(self, bindings: dict[str, Binding]):
        self._bindings = dict(bindings)
        self._active = False
        self._closed = False
        document = parse({"schemaVersion": 1, "kind": "portable.app-composition", "name": "Agentcraft",
            "members": [{"id": name, "capability": binding.capability, "requires": list(binding.requires)}
                        for name, binding in self._bindings.items()]})
        owners = set()

        def contribute(member):
            binding = self._bindings[member.id]
            close = None
            if binding.owned and id(binding.value) not in owners:
                close = getattr(binding.value, "aclose", None) or getattr(binding.value, "close", None)
                if not callable(close):
                    raise FrameworkError("owned_binding_requires_close", field=member.id)
                owners.add(id(binding.value))
            return Contribution(shutdown=close)

        self._composition = compose(document, resolve=allowlist({binding.capability: contribute for binding in bindings.values()}))

    def describe(self) -> dict:
        return {"framework": "agentcraft", "version": __version__, "active": self._active,
                "closed": self._closed, "configured": [
                    {"id": name, "capability": binding.capability, "owned": binding.owned,
                     "requires": list(binding.requires)} for name, binding in self._bindings.items()],
                "readiness": "unverified"}

    def get(self, name: str, expected: type[Value]) -> Value:
        if not self._active or self._closed:
            raise FrameworkError("framework_not_active")
        binding = self._bindings.get(name)
        if binding is None or not isinstance(binding.value, expected):
            raise FrameworkError("binding_type_or_name_mismatch", field=name)
        return binding.value

    def data(self, name: str):
        from azdata import DataConnector
        return self.get(name, DataConnector)

    def model(self, name: str):
        from llm_interface import Connection
        return self.get(name, Connection)

    async def __aenter__(self):
        if self._closed:
            raise FrameworkError("framework_closed")
        await self._composition.astartup()
        self._active = True
        return self

    async def aclose(self):
        if self._closed:
            return
        try:
            await self._composition.aclose()
        finally:
            self._active = False
            self._closed = True

    async def __aexit__(self, *exception):
        await self.aclose()


__all__ = ["Framework", "Binding", "CallerContext", "ExecutionBudget", "ExecutionContext", "FailureInfo", "FrameworkError"]
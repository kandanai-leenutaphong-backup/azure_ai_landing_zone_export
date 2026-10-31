"""Host-owned Copilot CLI options; no browser-selected executable or arbitrary argv."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LaunchOptions:
    mode: str = "interactive"
    max_autopilot_continues: int = 5
    reasoning_effort: str | None = None
    session_name: str | None = None
    screen_reader: bool = False
    mouse: bool = True

    def __post_init__(self) -> None:
        if self.mode not in {"interactive", "plan", "autopilot"}:
            raise ValueError("mode must be interactive, plan, or autopilot")
        if type(self.max_autopilot_continues) is not int or not 0 <= self.max_autopilot_continues <= 20:
            raise ValueError("autopilot continuation limit must be 0..20")
        if self.reasoning_effort is not None and self.reasoning_effort not in {
            "none", "minimal", "low", "medium", "high", "xhigh", "max",
        }:
            raise ValueError("unsupported reasoning effort")
        if self.session_name is not None and (
            not isinstance(self.session_name, str) or not self.session_name.strip()
            or len(self.session_name) > 80 or self.session_name.startswith("-")
            or any(ord(character) < 32 or ord(character) == 127 for character in self.session_name)
        ):
            raise ValueError("session name must be 1..80 printable characters, not an option")
        if type(self.screen_reader) is not bool or type(self.mouse) is not bool:
            raise ValueError("accessibility options must be booleans")

    def arguments(self) -> list[str]:
        arguments = ["--mode", self.mode]
        if self.mode == "autopilot":
            arguments += ["--max-autopilot-continues", str(self.max_autopilot_continues)]
        if self.reasoning_effort is not None:
            arguments += ["--reasoning-effort", self.reasoning_effort]
        if self.session_name is not None:
            arguments += ["--name", self.session_name]
        if self.screen_reader:
            arguments.append("--screen-reader")
        if not self.mouse:
            arguments.append("--no-mouse")
        return arguments

    def summary(self) -> dict:
        return {"mode": self.mode, "reasoning_effort": self.reasoning_effort,
                "session_name": self.session_name, "screen_reader": self.screen_reader,
                "max_autopilot_continues": self.max_autopilot_continues if self.mode == "autopilot" else None}
#!/usr/bin/env python3
"""Opt-in real Copilot PTY check: private state, offline loopback provider, no inference."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from pathlib import Path

from copilot_terminal import LaunchOptions, ProviderConfig, TerminalService

HEADERS = {'host': '127.0.0.1:8765', 'origin': 'http://127.0.0.1:8765',
           'content-type': 'application/json', 'x-copilot-terminal': '1'}
ANSI = re.compile(r'\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]')


class OfflineTestProvider(ProviderConfig):
    def environment(self, token: str, home: Path, path: str) -> dict[str, str]:
        return {**super().environment(token, home, path), 'COPILOT_OFFLINE': 'true'}


def await_output(terminal, pattern: str, *, after: int = 0, seconds: float = 45) -> int:
    deadline = time.monotonic() + seconds
    cursor = after
    collected = ''
    while time.monotonic() < deadline:
        output = terminal.output(cursor, wait=0.5)
        cursor = output['cursor']
        collected += output['output']
        if re.search(pattern, ANSI.sub('', collected), re.I):
            return cursor
        if not output['running']:
            raise AssertionError(f'CLI exited before native output matched {pattern!r}')
    raise AssertionError(f'Native CLI did not produce {pattern!r} before the deadline')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cli', required=True, type=Path)
    parser.add_argument('--plugin-dir', type=Path)
    args = parser.parse_args()
    cli = args.cli.resolve(strict=True)
    plugin_dirs = (args.plugin_dir.resolve(strict=True),) if args.plugin_dir else ()
    with tempfile.TemporaryDirectory(prefix='ghcp-native-') as directory:
        service = TerminalService(str(cli), OfflineTestProvider('https://127.0.0.1:1/v1', 'offline-test', model_id='gpt-5.4'),
                                  Path(directory), lambda: ('nonsecret-offline-fixture', time.time() + 900),
                                  path='/usr/bin:/bin', launch=LaunchOptions(mouse=False), plugin_dirs=plugin_dirs)
        try:
            status, info = service.handle('info', HEADERS, {})
            assert status == 200 and info.get('available'), info
            status, session = service.handle('start', HEADERS, {})
            assert status == 201, session
            terminal = service._lookup(session).terminal
            cursor = await_output(terminal, r'@ files|/ commands')
            for command, expected in (('/help', r'(interactive|commands|keyboard)'), ('/session info', r'(session id|workspace|working directory)')):
                assert service.handle('input', HEADERS, {**session, 'data': command})[0] == 200
                cursor = await_output(terminal, re.escape(command), after=cursor)
                assert service.handle('input', HEADERS, {**session, 'data': '\r'})[0] == 200
                cursor = await_output(terminal, expected, after=cursor)
                assert service.handle('input', HEADERS, {**session, 'data': '\x1b'})[0] == 200
                cursor = await_output(terminal, r'@ files|/ commands', after=cursor)
            if plugin_dirs:
                assert service.handle('resize', HEADERS, {**session, 'columns': 160, 'rows': 160})[0] == 200
                for command, expected in (
                    ('/skills', r'(?s)\u2713\s+protocol-regression-loop.*?Plugin-contributed'),
                    ('/agent', r'(?s)developer.*?plugin.*?orchestrator.*?plugin.*?overseer.*?plugin'),
                ):
                    assert service.handle('input', HEADERS, {**session, 'data': command})[0] == 200
                    cursor = await_output(terminal, re.escape(command), after=cursor)
                    assert service.handle('input', HEADERS, {**session, 'data': '\r'})[0] == 200
                    cursor = await_output(terminal, expected, after=cursor)
                    assert service.handle('input', HEADERS, {**session, 'data': '\x1b'})[0] == 200
                    cursor = await_output(terminal, r'@ files|/ commands', after=cursor)
            assert service.handle('resize', HEADERS, {**session, 'columns': 87, 'rows': 24})[0] == 200
            assert service.handle('input', HEADERS, {**session, 'key': 'wrong', 'data': 'unwanted'})[0] == 404
            assert service.handle('stop', HEADERS, session)[0] == 200
            assert terminal.process.poll() is not None
            assert service.handle('output', HEADERS, {**session, 'cursor': 0})[0] == 404
            print(json.dumps({'passed': True, 'cli': info['version'], 'native_commands': ['/help', '/session info'],
                              'native_plugin_workflow_and_agents': bool(plugin_dirs),
                              'resize': True, 'stop_revoked': True, 'model_calls': False,
                              'normal_profile_changed': False}))
        finally:
            service.close()


if __name__ == '__main__':
    main()
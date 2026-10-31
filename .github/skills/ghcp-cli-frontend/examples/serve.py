#!/usr/bin/env python3
"""Serve the built example on loopback with explicit fixture or provider configuration."""

from __future__ import annotations

import argparse
import json
import os
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from copilot_terminal import LaunchOptions, ProviderConfig, TerminalService

LIBRARY_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', required=True, type=Path)
    parser.add_argument('--sessions', required=True, type=Path)
    parser.add_argument('--port', type=int, default=8765)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--fixture', action='store_true')
    mode.add_argument('--cli', type=Path)
    mode.add_argument('--offline-cli', type=Path, help='real CLI with an unreachable loopback provider; native commands only')
    parser.add_argument('--endpoint')
    parser.add_argument('--deployment')
    parser.add_argument('--model-id')
    parser.add_argument('--token-env', default='GHCP_FRONTEND_TOKEN')
    parser.add_argument('--expires-at', type=float)
    parser.add_argument('--mode', choices=('interactive', 'plan', 'autopilot'), default='interactive')
    arguments = parser.parse_args()
    dist = arguments.dist.resolve()
    sessions = arguments.sessions.resolve()
    if not (dist / 'index.html').is_file():
        parser.error('--dist must contain the built example')
    if sessions.is_relative_to(LIBRARY_ROOT) or sessions.is_relative_to(Path.home()):
        parser.error('--sessions must be outside the library and user home')
    if any((ancestor / '.git').exists() for ancestor in (sessions, *sessions.parents)):
        parser.error('--sessions must be outside repository ancestry')
    if arguments.fixture:
        cli = Path(__file__).with_name('fixture_cli.py')
        provider = ProviderConfig('https://fixture.invalid', 'fixture')

        def issue_token():
            return 'nonsecret-fixture-token', time.time() + 3600
    elif arguments.offline_cli:
        class OfflineProvider(ProviderConfig):
            def environment(self, token, home, path):
                return {**super().environment(token, home, path), 'COPILOT_OFFLINE': 'true'}

        cli = arguments.offline_cli.resolve(strict=True)
        provider = OfflineProvider('https://127.0.0.1:1/v1', 'offline-test', model_id='gpt-5.4')

        def issue_token():
            return 'nonsecret-offline-fixture', time.time() + 3600
    else:
        if not all((arguments.endpoint, arguments.deployment, arguments.model_id, arguments.expires_at)):
            parser.error('real CLI mode requires endpoint, deployment, model-id and expires-at')
        cli = arguments.cli.resolve(strict=True)
        provider = ProviderConfig(arguments.endpoint, arguments.deployment, model_id=arguments.model_id)

        def issue_token():
            token = os.environ.get(arguments.token_env)
            if not token:
                raise ValueError('The host provider token is unavailable')
            return token, arguments.expires_at

    def source_loader(selection):
        if selection != {'uid': 'example', 'path': 'example.txt'}:
            raise PermissionError('Unknown example source')
        return 'example.txt', b'Local example source. No remote dataset.\n'

    service = TerminalService(str(cli), provider, sessions, issue_token, path=os.environ.get('PATH', '/usr/bin:/bin'),
                              source_loader=source_loader, launch=LaunchOptions(mode=arguments.mode))
    service.operations['prepare'] = lambda workspace, payload, headers: {
        'prompt': 'Inspect the local example source without modifying it.',
    }

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(dist), **kwargs)

        def log_message(self, *_args):
            pass

        def respond(self, status, body):
            encoded = json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            if self.path == '/example-info':
                label = 'PTY fixture' if arguments.fixture else 'Offline CLI' if arguments.offline_cli else 'Local Copilot CLI'
                self.respond(200, {'mode': label})
            else:
                super().do_GET()

        def do_POST(self):
            headers = {name.lower(): value for name, value in self.headers.items()}
            if not service.authorized(headers):
                self.respond(403, {'error': 'forbidden'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 131072:
                    raise ValueError('invalid body size')
                payload = json.loads(self.rfile.read(length))
            except (ValueError, json.JSONDecodeError):
                self.respond(400, {'error': 'bad_request'})
                return
            if not self.path.startswith('/api/terminal/'):
                self.respond(404, {'error': 'not_found'})
                return
            status, body = service.handle(self.path.removeprefix('/api/terminal/'), headers, payload)
            self.respond(status, body)

    server = ThreadingHTTPServer(('127.0.0.1', arguments.port), Handler)
    try:
        print(f'Example URL: http://127.0.0.1:{server.server_port}', flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        service.close()


if __name__ == '__main__':
    main()
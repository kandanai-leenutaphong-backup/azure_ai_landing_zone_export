#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${DEPLOY_PYTHON:-/usr/local/bin/python3}" "$ROOT/deploy/manage.py" "$@"

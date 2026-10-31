from pathlib import Path

import pytest

import publish


def test_export_excludes_state_databases_private_files_and_symlinks(tmp_path, monkeypatch):
    app = tmp_path / "applications/customer-service-multi-agent"
    app.mkdir(parents=True)
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    workflow = tmp_path / ".github/workflows"
    workflow.mkdir(parents=True)
    for name in ("main.py", "README.md", "customer.db", "token.env", "private.pem", ".env", ".env.json", ".env-template"):
        (app / name).write_text("synthetic")
    for name in ("evidence", "evaluation-artifacts", ".state", "__pycache__"):
        (app / name).mkdir()
        (app / name / "result.json").write_text("must not publish")
    (app / "linked.py").symlink_to(app / "main.py")
    for name in ("standalone-README.md", "standalone-copilot-instructions.md", "deploy.sh"):
        (deploy / name).write_text("safe")
    (workflow / "customer-service.yml").write_text("safe")
    monkeypatch.setattr(publish, "ROOT", tmp_path)
    monkeypatch.setattr(publish, "APP", app)
    exported = publish.sources()
    assert Path("applications/customer-service-multi-agent/main.py") in exported
    assert Path("applications/customer-service-multi-agent/.env-template") in exported
    assert not any(path.name in {"customer.db", "token.env", "private.pem", "linked.py", "result.json", ".env", ".env.json"} for path in exported)


def test_export_refuses_credential_shaped_source(tmp_path, monkeypatch):
    app = tmp_path / "app"
    app.mkdir()
    (app / "leak.py").write_bytes(b"-----BEGIN " + b"PRIVATE KEY-----")
    (tmp_path / "deploy").mkdir()
    monkeypatch.setattr(publish, "ROOT", tmp_path)
    monkeypatch.setattr(publish, "APP", app)
    with pytest.raises(ValueError, match="Credential-shaped"):
        publish.sources()

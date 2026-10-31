from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from manage import APP, ROOT, command

DESTINATION = "edsml-kl121/customer-service-production-multi-agent-azure"
APP_NAMES = {"Dockerfile", ".dockerignore", ".gitignore", ".env-template"}
APP_EXTENSIONS = {".py", ".txt", ".md", ".json", ".jsonl", ".html", ".css", ".js"}
DEPLOY_EXTENSIONS = {".py", ".sh", ".txt", ".md", ".bicep", ".env", ".kql"}
PROHIBITED = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b|"
    rb"\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b|"
    rb"\bAccountKey=[A-Za-z0-9+/]{30,}={0,2}|"
    rb"\bSharedAccessSignature=sv="
)


def sources() -> dict[Path, Path]:
    files = {}
    for path in APP.rglob("*"):
        if path.name.startswith(".env") and path.name != ".env-template":
            continue
        if not path.is_file() or path.is_symlink() or any(part in {"__pycache__", ".pytest_cache", ".venv", "evidence", "evaluation-artifacts", ".state"} for part in path.relative_to(APP).parts):
            continue
        if path.suffix in APP_EXTENSIONS or path.name in APP_NAMES:
            files[path.relative_to(ROOT)] = path
    for path in (ROOT / "deploy").rglob("*"):
        if path.name.startswith(".env") and path.name != ".env-template":
            continue
        if not path.is_file() or path.is_symlink() or any(part in {".state", "__pycache__", ".pytest_cache"} for part in path.relative_to(ROOT / "deploy").parts):
            continue
        if path.suffix in DEPLOY_EXTENSIONS or path.name == ".gitignore":
            files[path.relative_to(ROOT)] = path
    files[Path("README.md")] = ROOT / "deploy/standalone-README.md"
    files[Path(".github/copilot-instructions.md")] = ROOT / "deploy/standalone-copilot-instructions.md"
    files[Path(".github/workflows/customer-service.yml")] = ROOT / ".github/workflows/customer-service.yml"
    for relative, source in files.items():
        if PROHIBITED.search(source.read_bytes()):
            raise ValueError(f"Credential-shaped content blocks publication: {relative}")
    return files


def publish(destination: Path, push: bool, session_id: str | None) -> None:
    if push and (not session_id or not re.fullmatch(r"[0-9a-f-]{36}", session_id)):
        raise ValueError("Publishing requires the current Copilot session ID for the commit trailer.")
    destination = destination.resolve()
    if destination == ROOT or ROOT in destination.parents:
        raise ValueError("Standalone export must be outside the existing repository.")
    metadata = json.loads(command(["gh", "repo", "view", DESTINATION, "--json", "nameWithOwner,isPrivate,defaultBranchRef"]))
    if metadata["nameWithOwner"] != DESTINATION:
        raise ValueError("Repository ownership differs from the explicitly authorized target.")
    if not destination.exists():
        command(["gh", "repo", "clone", DESTINATION, str(destination)])
    actual = command(["git", "-C", str(destination), "remote", "get-url", "origin"])
    if actual.removesuffix(".git") not in {f"https://github.com/{DESTINATION}", f"git@github.com:{DESTINATION}"}:
        raise ValueError("Export directory points to a different Git remote.")
    existing = command(["git", "-C", str(destination), "status", "--porcelain"])
    if existing:
        raise RuntimeError("Standalone worktree is dirty; refusing to overwrite concurrent changes.")
    files = sources()
    manifest = []
    for relative, source in files.items():
        target = destination / relative
        if target.is_symlink() or destination not in target.resolve().parents:
            raise ValueError("Standalone target escapes the reviewed export root.")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        manifest.append({"path": str(relative), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
    (destination / "SOURCE-MANIFEST.json").write_text(json.dumps({
        "source_repository": "edsml-kl121/azure_ai_landing_zone_export",
        "scope": "allowlisted customer-service application, synthetic dataset and deployment owner",
        "files": sorted(manifest, key=lambda item: item["path"]),
    }, indent=2) + "\n")
    command(["git", "-C", str(destination), "add", "--", *[str(path) for path in files], "SOURCE-MANIFEST.json"])
    command([
        os.sys.executable, "-m", "pytest", "-q",
        str(destination / "applications/customer-service-multi-agent"), str(destination / "deploy"),
    ], output=True)
    command([os.sys.executable, str(destination / "deploy/validate_dataset.py")], output=True)
    if subprocess.run(["git", "-C", str(destination), "diff", "--cached", "--quiet"]).returncode == 0:
        print("Authorized standalone repository already matches the frozen export.")
        return
    if not push:
        print(json.dumps({"staging": str(destination), "files": len(manifest), "published": False}, indent=2))
        return
    command([
        "git", "-C", str(destination), "commit", "-m",
        "Build private Azure customer-service multi-agent demonstration\n\n"
        "Add structured observability, specialized judges, twenty frozen synthetic cases, "
        "fail-closed regression gates, protected SEA deployment and CI.\n\n"
        "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>\n"
        f"Copilot-Session: {session_id}",
    ], output=True)
    branch = command(["git", "-C", str(destination), "branch", "--show-current"])
    if branch != "main":
        command(["git", "-C", str(destination), "branch", "-m", "main"])
    command(["git", "-C", str(destination), "push", "-u", "origin", "main"], output=True)
    print(json.dumps({"repository": f"https://github.com/{DESTINATION}", "files": len(manifest), "published": True}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Allowlisted standalone export. Never git-init or reset the original repository.")
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--session-id", default=os.environ.get("COPILOT_SESSION_ID"))
    args = parser.parse_args()
    publish(args.destination, args.push, args.session_id)

"""Prove the four migrated distributions work without access to their checkout."""

import argparse
import importlib.metadata
import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    arguments = parser.parse_args()
    checkout = arguments.checkout.resolve()
    forbidden = []

    def guard(event, values):
        if event in {"socket.connect", "socket.getaddrinfo"}:
            forbidden.append(event)
            raise PermissionError("Network access is forbidden during installed acceptance")
        if event in {"open", "os.listdir", "os.scandir"} and values:
            value = values[0]
            if isinstance(value, (str, bytes, os.PathLike)):
                candidate = Path(os.fsdecode(value)).resolve()
                if candidate.is_relative_to(checkout):
                    forbidden.append(str(candidate))
                    raise PermissionError("Checkout access is forbidden during installed acceptance")

    sys.addaudithook(guard)
    try:
        (checkout / "README.md").read_bytes()
    except PermissionError:
        pass
    else:
        raise AssertionError("Checkout guard did not refuse its canary")
    assert len(forbidden) == 1
    forbidden.clear()

    from appcompose import CapabilityNotAllowed, Contribution, Response, Route, allowlist, compose, parse
    from appcompose.mcp import demo
    from investigation_notebook import InvestigationNotebook, NotebookError, load_schema
    from repository_inspection import architecture, catalogue, filesystem
    from workrecovery import ArtifactStore, MemoryStore, RecoverableJobs, RecoveryError, StoreTimeout
    from workrecovery.mcp import RecoveryTools, Settings

    checks = []
    with TemporaryDirectory(prefix="installed-capabilities-") as directory:
        root = Path(directory)
        os.chdir(root)
        document = parse({
            "schemaVersion": 1, "kind": "portable.app-composition", "name": "Installed example",
            "members": [{"id": "health", "capability": "health.read"}],
        })
        application = compose(document, resolve=allowlist({
            "health.read": lambda member: Contribution(routes=(
                Route("GET", "/health", lambda request: Response(body=b"ok")),
            )),
        }))
        assert application.dispatch("GET", "/health").status == 503
        application.startup()
        try:
            assert application.dispatch("GET", "/health").body == b"ok"
        finally:
            application.shutdown()
        assert application.shutdown() == ()
        try:
            compose(document, resolve=allowlist({}))
        except CapabilityNotAllowed:
            pass
        else:
            raise AssertionError("Unknown capability was accepted")
        demonstration = demo()
        assert demonstration["fixtures"] and demonstration["second_shutdown"] == ()
        checks.append("composition lifecycle, allowlist refusal, packaged demo resource")

        recovery_root = root / "recovery"
        jobs = RecoverableJobs(store=MemoryStore(timeout=StoreTimeout()), root=recovery_root)
        assert jobs.commit("retained", {"rows": [1, 2]}).state == "absent"
        restarted = RecoverableJobs(store=MemoryStore(), root=recovery_root)
        artifact = restarted.read("retained")
        assert artifact.payload == {"rows": [1, 2]}
        assert restarted.recommit(artifact).saved
        assert not list(restarted.pending())
        try:
            ArtifactStore(recovery_root).stage("../escape", {})
        except RecoveryError:
            pass
        else:
            raise AssertionError("Escaping run id was accepted")
        adapter = RecoveryTools(Settings(), root / "settings.json")
        try:
            adapter.stage("denied", "{}")
        except PermissionError:
            pass
        else:
            raise AssertionError("MCP staging without a grant was accepted")
        assert not (root / "artifacts").exists()
        checks.append("recovery restart/read-back, traversal and no-grant refusals")

        notebook = InvestigationNotebook(root / "notebook")
        assert not notebook.root.exists()
        assert "properties" in load_schema()
        draft_path = notebook.new_draft(
            "Portable finding", "Does the installed mechanism preserve evidence?",
            "repository-tooling", "method", "agent",
        )
        body = json.loads(draft_path.read_text(encoding="utf-8"))
        body.update({
            "summary": "Portable finding survives installed notebook publication.",
            "content": "The installed API publishes and retrieves synthetic evidence.",
            "findings": [{
                "statement": "Installed notebook publication is readable after reopening.",
                "evidence": [{"type": "observation", "reference": "installed_profile.py",
                              "detail": "Publication and retrieval complete with checkout access denied."}],
                "implications": [],
            }],
        })
        draft_path.write_text(json.dumps(body), encoding="utf-8")
        published_path, published = notebook.publish(draft_path)
        reopened = InvestigationNotebook(notebook.root)
        assert reopened.show(published["id"])["content"] == body["content"]
        assert len(reopened.search("Portable finding", 8)) == 1
        draft_path.write_text(json.dumps(body), encoding="utf-8")
        before = published_path.read_bytes()
        try:
            reopened.publish(draft_path)
        except NotebookError:
            pass
        else:
            raise AssertionError("Duplicate notebook publication was accepted")
        assert draft_path.exists() and published_path.read_bytes() == before
        assert not (notebook.root / "notebook.py").exists()
        assert not (notebook.root / "note.schema.json").exists()
        checks.append("notebook persistence, packaged schema, duplicate refusal without data copies")

        project = root / "project"
        (project / "core").mkdir(parents=True)
        (project / "app").mkdir()
        (project / "core/api.py").write_text("value = 1\n", encoding="utf-8")
        (project / "app/main.py").write_text("from core.api import value\n", encoding="utf-8")
        manifest = {"boundaries": [
            {"name": "core", "paths": ["core/*"], "may_depend_on": []},
            {"name": "app", "paths": ["app/*"], "may_depend_on": ["core"]},
        ]}
        (project / "architecture.json").write_text(json.dumps(manifest), encoding="utf-8")
        assert not architecture.check(project)["violations"]
        manifest["boundaries"][1]["may_depend_on"] = []
        (project / "architecture.json").write_text(json.dumps(manifest), encoding="utf-8")
        assert architecture.check(project)["violations"]
        inventory = filesystem.scan(project)
        assert inventory["complete"] and inventory["totals"]["files"] == 3
        assert filesystem.compare(inventory, inventory)["net_removed"]["files"] == 0
        try:
            filesystem.write_report(inventory, project / "invalid-report.json")
        except ValueError:
            pass
        else:
            raise AssertionError("Inventory output inside the measured root was accepted")
        metadata = root / "catalogue"
        (metadata / "skills/fixture").mkdir(parents=True)
        (metadata / "protocols").mkdir()
        (metadata / "skills/fixture/SKILL.md").write_text("# Synthetic fixture\n", encoding="utf-8")
        (metadata / "skills/catalogue.json").write_text(json.dumps({
            "schema_version": 1, "skills": [{"name": "fixture", "summary": "Portable fixture", "access": "guidance"}],
        }), encoding="utf-8")
        (metadata / "protocols/catalogue.json").write_text(
            json.dumps({"schema_version": 1, "protocols": []}), encoding="utf-8",
        )
        assert catalogue.report(metadata, name="fixture")["entries"][0]["content"] == "# Synthetic fixture\n"
        try:
            catalogue.contained_file(metadata, "../outside")
        except ValueError:
            pass
        else:
            raise AssertionError("Escaping catalogue path was accepted")
        checks.append("inspection graph, inventory, catalogue and matching scope refusals")
        os.chdir(Path(sys.prefix))

    origins = {}
    prefixes = ("appcompose", "workrecovery", "investigation_notebook", "repository_inspection")
    for name, module in tuple(sys.modules.items()):
        if name.split(".", 1)[0] in prefixes and getattr(module, "__file__", None):
            origin = Path(module.__file__).resolve()
            assert origin.is_relative_to(Path(sys.prefix).resolve()), (name, str(origin))
            origins[name] = str(origin)
    assert not forbidden, forbidden
    distributions = {name: importlib.metadata.version(name) for name in (
        "portable-app-composition", "recoverable-jobs", "investigation-notebook", "repository-inspection",
    )}
    print(json.dumps({"status": "passed", "checks": checks, "distributions": distributions,
                      "checkout_runtime_accesses": 0, "network_attempts": 0,
                      "module_origins": origins}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
import copy

import pytest

from workbooks import assert_owned, definitions


def test_reuses_hierarchy_and_only_projects_safe_log_fields():
    documents = definitions("/subscriptions/example/workspace")
    quality = documents["quality"]["items"]
    for tier, item in zip(("system", "journey", "agent"), quality[1:], strict=True):
        assert f'| where tier == "{tier}"' in item["content"]["query"]
        assert "arg_max(TimeGenerated, *) by run_id" in item["content"]["query"]
    operations = documents["operations"]["items"]
    for item in operations[1:]:
        assert 'ContainerAppName_s == "customer-service-multi-agent"' in item["content"]["query"]
    for item in operations[-2:]:
        assert "| project TimeGenerated, trace_id=tostring(event.trace_id)" in item["content"]["query"]
        assert "project Log_s" not in item["content"]["query"]


def test_refuses_foreign_workbook_or_workspace():
    owned = {"tags": {"project": "customer-service-multi-agent",
                      "capability": "observability-workbooks"},
             "properties": {"sourceId": "/workspace"}}
    assert_owned(owned, "/WORKSPACE")
    for path, key, value in (("tags", "project", "foreign"),
                             ("tags", "capability", "foreign"),
                             ("properties", "sourceId", "/other")):
        foreign = copy.deepcopy(owned)
        foreign[path][key] = value
        with pytest.raises(RuntimeError, match="not owned"):
            assert_owned(foreign, "/workspace")

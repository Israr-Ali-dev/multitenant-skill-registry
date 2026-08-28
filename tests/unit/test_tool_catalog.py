import pytest

from app.core.errors import ValidationDomainError
from app.domain.tool_catalog import validate_requested_tools


def test_known_safe_tools_pass_through():
    result = validate_requested_tools(["docs.read", "calendar.write"])
    assert result == ["docs.read", "calendar.write"]


def test_empty_list_is_valid():
    assert validate_requested_tools([]) == []


@pytest.mark.parametrize("tool", ["shell.exec", "db.drop_table", "files.delete_recursive"])
def test_destructive_tools_rejected(tool):
    with pytest.raises(ValidationDomainError) as exc_info:
        validate_requested_tools([tool])
    assert any(e["code"] == "tool_destructive" for e in exc_info.value.errors)


def test_unknown_tool_rejected():
    with pytest.raises(ValidationDomainError) as exc_info:
        validate_requested_tools(["not.a.real.tool"])
    assert any(e["code"] == "unknown_tool" for e in exc_info.value.errors)


def test_duplicate_tool_rejected():
    with pytest.raises(ValidationDomainError) as exc_info:
        validate_requested_tools(["docs.read", "docs.read"])
    assert any(e["code"] == "duplicate_tool" for e in exc_info.value.errors)


def test_too_many_tools_rejected():
    with pytest.raises(ValidationDomainError):
        validate_requested_tools(["docs.read"] * 21)

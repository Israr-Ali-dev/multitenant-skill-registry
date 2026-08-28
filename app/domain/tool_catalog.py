"""Known-tool registry and requested-tool validation.

See docs/ADR.md ADR-6: a skill *requesting* a tool never grants it any
capability. This module only decides whether a tool key is even a valid,
non-destructive thing to request — actual capability grants live in the
`tool_grants` table and are resolved separately at runtime-read time.
"""

from app.core.errors import ValidationDomainError

MAX_REQUESTED_TOOLS = 20

# key -> destructive?
KNOWN_TOOLS: dict[str, bool] = {
    "calendar.read": False,
    "calendar.write": False,
    "email.send": False,
    "docs.read": False,
    "docs.write": False,
    "reports.generate": False,
    "crm.read": False,
    "crm.write": False,
    "tasks.create": False,
    "tasks.read": False,
    # Destructive / not requestable under any circumstance.
    "shell.exec": True,
    "db.drop_table": True,
    "files.delete_recursive": True,
    "network.raw_socket": True,
}


def validate_requested_tools(requested_tools: list[str]) -> list[str]:
    if len(requested_tools) > MAX_REQUESTED_TOOLS:
        raise ValidationDomainError(
            f"A skill may request at most {MAX_REQUESTED_TOOLS} tools "
            f"({len(requested_tools)} were given).",
            error_code="too-many-tools",
        )

    seen: set[str] = set()
    clean: list[str] = []  # de-duplicated, order-preserving
    errors = []
    for tool in requested_tools:
        if tool in seen:
            errors.append({"field": "requested_tools", "code": "duplicate_tool", "tool": tool})
            continue
        seen.add(tool)

        if tool not in KNOWN_TOOLS:
            errors.append({"field": "requested_tools", "code": "unknown_tool", "tool": tool})
            continue

        if KNOWN_TOOLS[tool]:
            errors.append({"field": "requested_tools", "code": "tool_destructive", "tool": tool})
            continue

        clean.append(tool)

    if errors:
        raise ValidationDomainError(
            "One or more requested tools are invalid or not permitted.",
            errors=errors,
            error_code="tool-not-permitted",
        )

    return clean

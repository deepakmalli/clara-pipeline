"""
diff_patch.py - Generate diffs and changelogs between v1 and v2 Account Memos and Agent Specs.

Produces:
- Detailed changelog (JSON and Markdown)
- Side-by-side comparison data for the diff viewer
"""

import json
from datetime import datetime
from deepdiff import DeepDiff


def generate_changelog(v1_memo: dict, v2_memo: dict, account_id: str) -> dict:
    """
    Compare v1 and v2 memos and generate a structured changelog.
    Returns a dict with all changes categorized.
    """
    diff = DeepDiff(v1_memo, v2_memo, ignore_order=True, verbose_level=2)

    changes = []

    # Values that changed
    if "values_changed" in diff:
        for path, detail in diff["values_changed"].items():
            field = _clean_path(path)
            changes.append({
                "type": "modified",
                "field": field,
                "from": detail.get("old_value"),
                "to": detail.get("new_value"),
                "reason": "Updated during onboarding",
            })

    # New items added
    if "dictionary_item_added" in diff:
        for path in diff["dictionary_item_added"]:
            field = _clean_path(path)
            new_val = _resolve_path(v2_memo, path)
            changes.append({
                "type": "added",
                "field": field,
                "value": new_val,
                "reason": "New information from onboarding",
            })

    # Items removed
    if "dictionary_item_removed" in diff:
        for path in diff["dictionary_item_removed"]:
            field = _clean_path(path)
            old_val = _resolve_path(v1_memo, path)
            changes.append({
                "type": "removed",
                "field": field,
                "value": old_val,
                "reason": "Removed during onboarding update",
            })

    # Items added to lists
    if "iterable_item_added" in diff:
        for path, value in diff["iterable_item_added"].items():
            field = _clean_path(path)
            changes.append({
                "type": "list_item_added",
                "field": field,
                "value": value,
                "reason": "Added during onboarding",
            })

    # Items removed from lists
    if "iterable_item_removed" in diff:
        for path, value in diff["iterable_item_removed"].items():
            field = _clean_path(path)
            changes.append({
                "type": "list_item_removed",
                "field": field,
                "value": value,
                "reason": "Removed during onboarding",
            })

    # Type changes
    if "type_changes" in diff:
        for path, detail in diff["type_changes"].items():
            field = _clean_path(path)
            changes.append({
                "type": "type_changed",
                "field": field,
                "from": str(detail.get("old_value")),
                "to": str(detail.get("new_value")),
                "reason": "Updated during onboarding",
            })

    changelog = {
        "account_id": account_id,
        "version_from": "v1",
        "version_to": "v2",
        "timestamp": datetime.now().isoformat(),
        "total_changes": len(changes),
        "changes": changes,
        "summary": _generate_summary(changes),
    }

    return changelog


def changelog_to_markdown(changelog: dict) -> str:
    """Convert a changelog dict to a readable Markdown file."""
    lines = [
        f"# Changelog: {changelog['account_id']}",
        f"",
        f"**Version**: {changelog['version_from']} → {changelog['version_to']}",
        f"**Date**: {changelog['timestamp']}",
        f"**Total Changes**: {changelog['total_changes']}",
        f"",
        f"## Summary",
        f"",
        changelog.get("summary", "No changes detected."),
        f"",
        f"## Detailed Changes",
        f"",
    ]

    for i, change in enumerate(changelog.get("changes", []), 1):
        change_type = change.get("type", "unknown")
        field = change.get("field", "unknown")

        if change_type == "modified":
            lines.append(f"### {i}. Modified: `{field}`")
            lines.append(f"- **From**: {json.dumps(change.get('from'), default=str)}")
            lines.append(f"- **To**: {json.dumps(change.get('to'), default=str)}")
        elif change_type == "added":
            lines.append(f"### {i}. Added: `{field}`")
            lines.append(f"- **Value**: {json.dumps(change.get('value'), default=str)}")
        elif change_type == "removed":
            lines.append(f"### {i}. Removed: `{field}`")
            lines.append(f"- **Value**: {json.dumps(change.get('value'), default=str)}")
        elif change_type in ("list_item_added", "list_item_removed"):
            action = "Added to" if "added" in change_type else "Removed from"
            lines.append(f"### {i}. {action}: `{field}`")
            lines.append(f"- **Value**: {json.dumps(change.get('value'), default=str)}")
        else:
            lines.append(f"### {i}. {change_type.title()}: `{field}`")

        lines.append(f"- **Reason**: {change.get('reason', 'N/A')}")
        lines.append("")

    if not changelog.get("changes"):
        lines.append("_No changes detected between v1 and v2._")

    return "\n".join(lines)


def _generate_summary(changes: list) -> str:
    """Generate a human-readable summary of changes."""
    if not changes:
        return "No changes were detected between v1 and v2."

    modified = sum(1 for c in changes if c["type"] == "modified")
    added = sum(1 for c in changes if c["type"] in ("added", "list_item_added"))
    removed = sum(1 for c in changes if c["type"] in ("removed", "list_item_removed"))

    parts = []
    if modified:
        parts.append(f"{modified} field(s) modified")
    if added:
        parts.append(f"{added} field(s)/item(s) added")
    if removed:
        parts.append(f"{removed} field(s)/item(s) removed")

    # Highlight key changes
    key_fields = {"business_hours", "emergency_definition", "emergency_routing_rules",
                  "services_supported", "call_transfer_rules"}
    important_changes = [c for c in changes if any(kf in c.get("field", "") for kf in key_fields)]

    summary = f"Total: {len(changes)} changes ({', '.join(parts)})."
    if important_changes:
        summary += f"\n\n**Key changes**: "
        summary += "; ".join(
            f"`{c['field']}` was {c['type']}" for c in important_changes[:5]
        )
        summary += "."

    return summary


def _clean_path(deepdiff_path: str) -> str:
    """Convert DeepDiff path notation to readable dot notation."""
    # root['business_hours']['start'] -> business_hours.start
    path = deepdiff_path.replace("root", "")
    path = path.replace("['", ".").replace("']", "")
    path = path.replace("[", ".").replace("]", "")
    if path.startswith("."):
        path = path[1:]
    return path


def _resolve_path(data: dict, deepdiff_path: str):
    """Resolve a DeepDiff path to get the actual value."""
    import re
    keys = re.findall(r"\['([^']+)'\]|\[(\d+)\]", deepdiff_path)
    current = data
    try:
        for str_key, int_key in keys:
            if str_key:
                current = current[str_key]
            elif int_key:
                current = current[int(int_key)]
        return current
    except (KeyError, IndexError, TypeError):
        return None

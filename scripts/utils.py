"""
utils.py - Shared utilities for the Clara pipeline.
"""

import os
import re
import json
import hashlib
from datetime import datetime
from slugify import slugify


def generate_account_id(company_name: str) -> str:
    """Generate a stable, URL-safe account_id from a company name."""
    if not company_name:
        return f"unknown-{hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8]}"
    return slugify(company_name, max_length=50)


def ensure_dir(path: str):
    """Create directory if it doesn't exist."""
    os.makedirs(path, exist_ok=True)


def save_json(data: dict, filepath: str):
    """Save dict as formatted JSON."""
    ensure_dir(os.path.dirname(filepath))
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    print(f"  [SAVED] {filepath}")


def load_json(filepath: str) -> dict:
    """Load JSON from file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def read_transcript(filepath: str) -> str:
    """Read a transcript text file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read().strip()


def extract_json_from_text(text: str) -> dict:
    """
    Extract a JSON object from LLM response text.
    Handles markdown code blocks, extra text before/after JSON, etc.
    """
    # Try to find JSON in markdown code block first
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_block:
        text = code_block.group(1).strip()

    # Try to find the outermost { ... }
    brace_start = text.find("{")
    if brace_start == -1:
        raise ValueError(f"No JSON object found in LLM response:\n{text[:500]}")

    # Find the matching closing brace
    depth = 0
    for i in range(brace_start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                json_str = text[brace_start : i + 1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError as e:
                    # Try to fix common LLM JSON issues
                    json_str = _fix_common_json_errors(json_str)
                    return json.loads(json_str)

    raise ValueError(f"Malformed JSON in LLM response:\n{text[:500]}")


def _fix_common_json_errors(json_str: str) -> str:
    """Attempt to fix common LLM JSON mistakes."""
    # Remove trailing commas before } or ]
    json_str = re.sub(r",\s*([}\]])", r"\1", json_str)
    # Replace single quotes with double quotes (carefully)
    # Only if there are no double quotes at all
    if '"' not in json_str:
        json_str = json_str.replace("'", '"')
    return json_str


def get_output_dir(base_dir: str, account_id: str, version: str) -> str:
    """Get the output directory for an account version."""
    return os.path.join(base_dir, "accounts", account_id, version)


def timestamp() -> str:
    """Current ISO timestamp."""
    return datetime.now().isoformat()


def find_v1_account(outputs_dir: str, account_id: str = None, company_name: str = None) -> str | None:
    """
    Find a v1 account directory. Searches by account_id first,
    then by fuzzy matching on company_name in memos.
    Returns the account_id if found, None otherwise.
    """
    accounts_dir = os.path.join(outputs_dir, "accounts")
    if not os.path.exists(accounts_dir):
        return None

    # Direct match by account_id
    if account_id:
        v1_dir = os.path.join(accounts_dir, account_id, "v1")
        if os.path.exists(v1_dir):
            return account_id

    # Search by company name in existing memos
    if company_name:
        target_slug = slugify(company_name, max_length=50)
        for dirname in os.listdir(accounts_dir):
            # Check slug match
            if dirname == target_slug:
                v1_dir = os.path.join(accounts_dir, dirname, "v1")
                if os.path.exists(v1_dir):
                    return dirname

            # Check memo content
            memo_path = os.path.join(accounts_dir, dirname, "v1", "account_memo_v1.json")
            if os.path.exists(memo_path):
                try:
                    memo = load_json(memo_path)
                    if memo.get("company_name", "").lower().strip() == company_name.lower().strip():
                        return dirname
                except (json.JSONDecodeError, KeyError):
                    continue

    return None


def list_accounts(outputs_dir: str) -> list[str]:
    """List all account IDs in the outputs directory."""
    accounts_dir = os.path.join(outputs_dir, "accounts")
    if not os.path.exists(accounts_dir):
        return []
    return [
        d for d in os.listdir(accounts_dir)
        if os.path.isdir(os.path.join(accounts_dir, d))
        and d != ".gitkeep"
    ]

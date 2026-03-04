"""
extract.py - Extract structured Account Memo from demo/onboarding transcripts.

Pipeline A: Demo transcript → Account Memo v1
Pipeline B: Onboarding transcript → Update patch for Account Memo
"""

import os
from scripts.llm_client import LLMClient
from scripts.utils import extract_json_from_text, read_transcript, generate_account_id


# Default memo schema - ensures all fields are present even if LLM misses them
MEMO_SCHEMA = {
    "account_id": None,
    "company_name": None,
    "business_hours": {
        "days": None,
        "start": None,
        "end": None,
        "timezone": None,
    },
    "office_address": None,
    "services_supported": [],
    "emergency_definition": [],
    "emergency_routing_rules": {
        "primary_contact": None,
        "secondary_contact": None,
        "call_order": [],
        "fallback_action": None,
    },
    "non_emergency_routing_rules": {
        "during_hours": None,
        "after_hours": None,
    },
    "call_transfer_rules": {
        "timeout_seconds": 30,
        "retries": 2,
        "fail_message": "I'm sorry I wasn't able to reach anyone right now. I've noted your information and someone will call you back shortly.",
    },
    "integration_constraints": [],
    "after_hours_flow_summary": None,
    "office_hours_flow_summary": None,
    "questions_or_unknowns": [],
    "notes": "",
}


def _load_prompt_template(template_name: str) -> str:
    """Load a prompt template from the templates directory."""
    template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
    template_path = os.path.join(template_dir, template_name)
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


def _merge_with_schema(extracted: dict, schema: dict = None) -> dict:
    """
    Merge extracted data with the default schema to ensure all fields exist.
    Extracted values take precedence over defaults.
    """
    if schema is None:
        schema = MEMO_SCHEMA.copy()

    result = {}
    for key, default_value in schema.items():
        if key in extracted and extracted[key] is not None:
            if isinstance(default_value, dict) and isinstance(extracted[key], dict):
                # Recursive merge for nested dicts
                result[key] = _merge_with_schema(extracted[key], default_value)
            else:
                result[key] = extracted[key]
        else:
            if isinstance(default_value, dict):
                result[key] = default_value.copy()
            elif isinstance(default_value, list):
                result[key] = default_value.copy()
            else:
                result[key] = default_value

    # Keep any extra fields the LLM extracted that aren't in our schema
    for key, value in extracted.items():
        if key not in result:
            result[key] = value

    return result


def extract_demo_memo(transcript_text: str, llm: LLMClient = None) -> dict:
    """
    Extract Account Memo from a demo call transcript.
    Returns a structured dict matching the memo schema.
    """
    if llm is None:
        llm = LLMClient()

    # Load and fill the extraction prompt
    prompt_template = _load_prompt_template("extraction_prompt.txt")
    prompt = prompt_template.replace("{{TRANSCRIPT}}", transcript_text)

    print("  [EXTRACT] Sending demo transcript to LLM for extraction...")
    raw_response = llm.generate(prompt)
    print("  [EXTRACT] LLM response received. Parsing JSON...")

    # Parse the JSON from LLM response
    extracted = extract_json_from_text(raw_response)

    # Merge with schema to ensure all fields exist
    memo = _merge_with_schema(extracted)

    # Generate account_id from company name if not set
    if not memo.get("account_id"):
        memo["account_id"] = generate_account_id(memo.get("company_name", ""))

    return memo


def extract_onboarding_updates(transcript_text: str, existing_memo: dict, llm: LLMClient = None) -> dict:
    """
    Extract updates from an onboarding call/form and return the update patch.
    The patch contains only fields that should be changed or added.
    """
    if llm is None:
        llm = LLMClient()

    import json
    prompt_template = _load_prompt_template("onboarding_extraction_prompt.txt")
    prompt = prompt_template.replace("{{TRANSCRIPT}}", transcript_text)
    prompt = prompt.replace("{{EXISTING_MEMO}}", json.dumps(existing_memo, indent=2))

    print("  [EXTRACT] Sending onboarding transcript to LLM for update extraction...")
    raw_response = llm.generate(prompt)
    print("  [EXTRACT] LLM response received. Parsing updates...")

    updates = extract_json_from_text(raw_response)
    return updates


def apply_updates(existing_memo: dict, updates: dict) -> dict:
    """
    Apply extracted onboarding updates to the existing memo.
    Creates a v2 memo. Lists are merged (not replaced), dicts are deep-merged.
    """
    import copy
    v2_memo = copy.deepcopy(existing_memo)

    for key, new_value in updates.items():
        if key in ("account_id",):
            # Never overwrite account_id
            continue

        if key not in v2_memo:
            v2_memo[key] = new_value
            continue

        old_value = v2_memo[key]

        if isinstance(old_value, dict) and isinstance(new_value, dict):
            # Deep merge dicts
            for sub_key, sub_val in new_value.items():
                if sub_val is not None:
                    old_value[sub_key] = sub_val
        elif isinstance(old_value, list) and isinstance(new_value, list):
            # Merge lists, avoiding duplicates
            combined = list(old_value)
            for item in new_value:
                if item not in combined:
                    combined.append(item)
            v2_memo[key] = combined
        else:
            # Simple replacement
            if new_value is not None:
                v2_memo[key] = new_value

    return v2_memo

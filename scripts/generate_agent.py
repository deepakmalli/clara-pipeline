"""
generate_agent.py - Generate Retell AI Agent Draft Spec from Account Memo.

Produces a complete agent configuration with:
- System prompt (business hours + after hours flows)
- Voice settings
- Call transfer protocols
- Fallback protocols
- Tool invocation placeholders
"""

import os
import json
from scripts.utils import timestamp


def _build_system_prompt(memo: dict) -> str:
    """
    Generate the full system prompt for the Retell AI agent.
    Includes business hours flow and after hours flow with proper
    call handling, transfer, and fallback logic.
    """
    company = memo.get("company_name", "the company")
    bh = memo.get("business_hours", {}) or {}
    address = memo.get("office_address", "")
    services = memo.get("services_supported", [])
    emergencies = memo.get("emergency_definition", [])
    emergency_routing = memo.get("emergency_routing_rules", {}) or {}
    non_emergency_routing = memo.get("non_emergency_routing_rules", {}) or {}
    transfer_rules = memo.get("call_transfer_rules", {}) or {}
    integration = memo.get("integration_constraints", [])
    after_hours_summary = memo.get("after_hours_flow_summary", "")
    office_hours_summary = memo.get("office_hours_flow_summary", "")

    # Format business hours
    bh_days = bh.get("days", "Monday through Friday")
    bh_start = bh.get("start", "8:00 AM")
    bh_end = bh.get("end", "5:00 PM")
    bh_tz = bh.get("timezone", "Eastern Time")

    # Format services list
    services_str = ", ".join(services) if services else "general services"

    # Format emergency triggers
    emergency_str = ""
    if emergencies:
        emergency_str = "Emergency situations include: " + ", ".join(emergencies) + "."

    # Format emergency routing
    primary = emergency_routing.get("primary_contact", "the on-call technician")
    secondary = emergency_routing.get("secondary_contact", "the owner or manager")
    call_order = emergency_routing.get("call_order", [])
    fallback_action = emergency_routing.get(
        "fallback_action",
        "Assure the caller that their information has been recorded and someone will return their call as quickly as possible."
    )

    # Transfer rules
    timeout = transfer_rules.get("timeout_seconds", 30)
    retries = transfer_rules.get("retries", 2)
    fail_msg = transfer_rules.get(
        "fail_message",
        "I'm sorry, I wasn't able to reach anyone right now. I've noted your information and someone will call you back shortly."
    )

    # Integration constraints
    constraints_str = ""
    if integration:
        constraints_str = "\n\nIMPORTANT CONSTRAINTS:\n" + "\n".join(f"- {c}" for c in integration)

    prompt = f"""You are a professional, friendly virtual receptionist for {company}. You handle incoming calls with warmth, efficiency, and accuracy. You speak naturally and conversationally — never robotic.

COMPANY INFORMATION:
- Company: {company}
- Business Hours: {bh_days}, {bh_start} to {bh_end} ({bh_tz})
- Address: {address or "Not specified"}
- Services: {services_str}

{emergency_str}

===== DURING BUSINESS HOURS FLOW =====

1. GREETING: Answer warmly.
   "Thank you for calling {company}, this is Clara. How can I help you today?"

2. DETERMINE PURPOSE: Listen to the caller's reason. Ask a brief clarifying question ONLY if the purpose is unclear. Do not ask unnecessary questions.

3. COLLECT ESSENTIAL INFO (only what is needed):
   - Caller's name
   - Callback phone number
   - Brief description of the issue or request

4. ROUTE OR TRANSFER:
   - For service requests and general inquiries during business hours: {non_emergency_routing.get("during_hours", "Transfer the call to the office.")}
   - Attempt to transfer the call. Wait up to {timeout} seconds for an answer.
   - If the first attempt fails, retry up to {retries} time(s).

5. IF TRANSFER FAILS:
   Say: "{fail_msg}"
   Confirm you have their name and number. Assure them someone will follow up.

6. WRAP UP:
   "Is there anything else I can help you with?"
   If not: "Thank you for calling {company}. Have a great day!"

===== AFTER HOURS FLOW =====

1. GREETING: Answer warmly with after-hours context.
   "Thank you for calling {company}. Our office is currently closed. Our business hours are {bh_days}, {bh_start} to {bh_end} {bh_tz}. How can I help you?"

2. DETERMINE PURPOSE AND URGENCY:
   - Ask the caller what they need help with.
   - Determine if this is an emergency situation.

3. IF NON-EMERGENCY:
   - Collect the caller's name and phone number.
   - Let them know someone will return their call during business hours.
   - {non_emergency_routing.get("after_hours", "Take a message and assure a callback during business hours.")}
   - "Is there anything else I can help you with?"
   - Close the call politely.

4. IF EMERGENCY:
   - Confirm the emergency: "I understand this is urgent. Let me get some information so we can get help to you right away."
   - Collect IMMEDIATELY:
     a. Caller's full name
     b. Callback phone number
     c. Service address where the emergency is occurring
     d. Brief description of the emergency
   - Do NOT ask unnecessary questions. Speed is critical.

5. EMERGENCY TRANSFER:
   - Attempt to reach {primary} first.
   - If {primary} does not answer within {timeout} seconds, try {secondary}.
   {"- Call order: " + " → ".join(call_order) if call_order else ""}
   - Retry up to {retries} time(s) per contact.

6. IF ALL EMERGENCY TRANSFERS FAIL:
   {fallback_action}
   Say: "I've recorded all your information and marked this as urgent. Someone from our team will contact you as soon as possible."

7. WRAP UP:
   "Is there anything else I can help you with?"
   If not: "Thank you for calling {company}. Help is on the way."
{constraints_str}

===== GENERAL RULES =====
- NEVER mention internal systems, tools, or technical processes to the caller.
- NEVER say you are an AI, bot, or virtual assistant unless directly asked.
- Keep calls concise. Only collect information needed for routing and dispatch.
- Be empathetic and professional at all times.
- If you are unsure about something, say "Let me make a note of that and have someone follow up with you."
- Speak in natural, conversational language. Avoid jargon.
"""

    # Add custom office/after-hours notes if available
    if office_hours_summary:
        prompt += f"\nADDITIONAL OFFICE HOURS NOTES:\n{office_hours_summary}\n"
    if after_hours_summary:
        prompt += f"\nADDITIONAL AFTER HOURS NOTES:\n{after_hours_summary}\n"

    return prompt.strip()


def generate_agent_spec(memo: dict, version: str = "v1") -> dict:
    """
    Generate a complete Retell Agent Draft Spec from an Account Memo.

    Returns a dict that can be saved as JSON or YAML, matching the
    structure needed for Retell agent configuration.
    """
    company = memo.get("company_name", "Unknown Company")
    bh = memo.get("business_hours", {}) or {}
    transfer_rules = memo.get("call_transfer_rules", {}) or {}

    system_prompt = _build_system_prompt(memo)

    spec = {
        "agent_name": f"{company} - Clara Agent",
        "version": version,
        "created_at": timestamp(),
        "voice_style": {
            "voice": "female",
            "tone": "professional, warm, concise",
            "speed": "natural",
            "language": "en-US",
        },
        "system_prompt": system_prompt,
        "key_variables": {
            "company_name": company,
            "timezone": bh.get("timezone", "Eastern Time"),
            "business_hours": {
                "days": bh.get("days"),
                "start": bh.get("start"),
                "end": bh.get("end"),
            },
            "office_address": memo.get("office_address"),
            "emergency_triggers": memo.get("emergency_definition", []),
            "emergency_routing": memo.get("emergency_routing_rules", {}),
        },
        "tool_invocation_placeholders": [
            {
                "name": "transfer_call",
                "description": "Transfer the active call to a specified phone number",
                "parameters": {"phone_number": "string", "timeout_seconds": "integer"},
                "note": "This tool is invoked silently. Never mention it to the caller.",
            },
            {
                "name": "log_call",
                "description": "Log call details to the CRM/dispatch system",
                "parameters": {
                    "caller_name": "string",
                    "phone_number": "string",
                    "purpose": "string",
                    "is_emergency": "boolean",
                    "address": "string",
                    "notes": "string",
                },
                "note": "This tool is invoked silently. Never mention it to the caller.",
            },
            {
                "name": "send_notification",
                "description": "Send an urgent notification to on-call staff",
                "parameters": {"message": "string", "priority": "string"},
                "note": "This tool is invoked silently. Never mention it to the caller.",
            },
        ],
        "call_transfer_protocol": {
            "timeout_seconds": transfer_rules.get("timeout_seconds", 30),
            "max_retries": transfer_rules.get("retries", 2),
            "retry_interval_seconds": 5,
            "on_transfer_success": "Introduce the caller briefly if possible, then disconnect.",
            "on_transfer_fail": transfer_rules.get(
                "fail_message",
                "I'm sorry, I wasn't able to reach anyone right now. I've noted your information and someone will call you back shortly."
            ),
        },
        "fallback_protocol": {
            "when": "All transfer attempts exhausted",
            "actions": [
                "Confirm caller's name and callback number",
                "Summarize the issue or request",
                "Assure the caller that the message has been recorded",
                "Mark as urgent if emergency",
                "Provide estimated callback timeframe if known",
                "Close the call politely",
            ],
        },
        "metadata": {
            "account_id": memo.get("account_id"),
            "source_version": version,
            "generated_by": "clara-pipeline",
        },
    }

    return spec

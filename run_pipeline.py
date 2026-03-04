#!/usr/bin/env python3
"""
run_pipeline.py - Main CLI entry point for the Clara Automation Pipeline.

Usage:
    # Process a single demo call transcript → v1 outputs
    python run_pipeline.py demo --input dataset/demo/call1.txt

    # Process a single onboarding transcript → v2 outputs
    python run_pipeline.py onboarding --input dataset/onboarding/call1.txt --account-id acme-plumbing

    # Batch process all files in dataset/
    python run_pipeline.py batch

    # List all processed accounts
    python run_pipeline.py list
"""

import os
import sys
import json
import argparse
import traceback
from datetime import datetime
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scripts.llm_client import LLMClient
from scripts.extract import extract_demo_memo, extract_onboarding_updates, apply_updates
from scripts.generate_agent import generate_agent_spec
from scripts.diff_patch import generate_changelog, changelog_to_markdown
from scripts.task_tracker import TaskTracker
from scripts.utils import (
    save_json,
    load_json,
    read_transcript,
    get_output_dir,
    ensure_dir,
    find_v1_account,
    list_accounts,
    generate_account_id,
    timestamp,
)

load_dotenv()

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "outputs")
DATASET_DIR = os.getenv("DATASET_DIR", "dataset")


def pipeline_a_demo(transcript_path: str, llm: LLMClient, tracker: TaskTracker) -> dict:
    """
    Pipeline A: Demo Call → Preliminary Agent (v1)

    1. Read transcript
    2. Extract Account Memo via LLM
    3. Generate Agent Spec from memo
    4. Save v1 outputs
    5. Create tracking task
    """
    print(f"\n{'='*60}")
    print(f"  PIPELINE A: Demo Call → v1 Agent")
    print(f"  Input: {transcript_path}")
    print(f"{'='*60}")

    # Step 1: Read transcript
    print("\n[Step 1/5] Reading transcript...")
    transcript = read_transcript(transcript_path)
    print(f"  Transcript length: {len(transcript)} characters")

    # Step 2: Extract Account Memo
    print("\n[Step 2/5] Extracting account memo from transcript...")
    memo = extract_demo_memo(transcript, llm)
    account_id = memo["account_id"]
    company_name = memo.get("company_name", "Unknown")
    print(f"  Account ID: {account_id}")
    print(f"  Company: {company_name}")

    # Check if v1 already exists (idempotency)
    v1_dir = get_output_dir(OUTPUT_DIR, account_id, "v1")
    memo_path = os.path.join(v1_dir, "account_memo_v1.json")
    if os.path.exists(memo_path):
        print(f"  [NOTE] v1 already exists for {account_id}. Overwriting (idempotent).")

    # Step 3: Generate Agent Spec
    print("\n[Step 3/5] Generating Retell Agent Draft Spec...")
    agent_spec = generate_agent_spec(memo, version="v1")
    print(f"  Agent: {agent_spec['agent_name']}")

    # Step 4: Save outputs
    print("\n[Step 4/5] Saving v1 outputs...")
    save_json(memo, os.path.join(v1_dir, "account_memo_v1.json"))
    save_json(agent_spec, os.path.join(v1_dir, "agent_spec_v1.json"))

    # Also save the raw transcript reference
    metadata = {
        "source_file": os.path.basename(transcript_path),
        "source_path": transcript_path,
        "pipeline": "A",
        "version": "v1",
        "processed_at": timestamp(),
        "account_id": account_id,
        "company_name": company_name,
    }
    save_json(metadata, os.path.join(v1_dir, "metadata.json"))

    # Step 5: Create tracking task
    print("\n[Step 5/5] Creating tracking task...")
    task = tracker.create_task(account_id, company_name, "v1", "pending_review")

    print(f"\n{'='*60}")
    print(f"  ✓ Pipeline A complete for: {company_name}")
    print(f"  ✓ Outputs saved to: {v1_dir}")
    print(f"{'='*60}\n")

    return {
        "account_id": account_id,
        "company_name": company_name,
        "version": "v1",
        "output_dir": v1_dir,
        "status": "success",
    }


def pipeline_b_onboarding(
    transcript_path: str,
    account_id: str = None,
    llm: LLMClient = None,
    tracker: TaskTracker = None,
) -> dict:
    """
    Pipeline B: Onboarding → Agent Modification (v2)

    1. Read onboarding transcript
    2. Find matching v1 account
    3. Extract updates from onboarding
    4. Apply updates to create v2 memo
    5. Generate v2 Agent Spec
    6. Generate changelog
    7. Save v2 outputs
    8. Update tracking task
    """
    print(f"\n{'='*60}")
    print(f"  PIPELINE B: Onboarding → v2 Agent Update")
    print(f"  Input: {transcript_path}")
    print(f"{'='*60}")

    # Step 1: Read onboarding transcript
    print("\n[Step 1/8] Reading onboarding transcript...")
    transcript = read_transcript(transcript_path)
    print(f"  Transcript length: {len(transcript)} characters")

    # Step 2: Find matching v1 account
    print("\n[Step 2/8] Finding matching v1 account...")

    if account_id:
        matched_id = find_v1_account(OUTPUT_DIR, account_id=account_id)
    else:
        # Try to extract company name from onboarding to match
        # First do a quick LLM call to get the company name
        company_prompt = (
            "What is the company name discussed in this transcript? "
            "Reply with ONLY the company name, nothing else.\n\n"
            f"TRANSCRIPT:\n{transcript[:2000]}"
        )
        company_name_raw = llm.generate(company_prompt).strip().strip('"').strip("'")
        print(f"  Detected company: {company_name_raw}")
        matched_id = find_v1_account(OUTPUT_DIR, company_name=company_name_raw)

        # If still not found, try using the filename
        if not matched_id:
            basename = os.path.splitext(os.path.basename(transcript_path))[0]
            # Try common naming patterns: "onboarding_company-name" or "company-name_onboarding"
            for suffix in ["_onboarding", "-onboarding", "_ob", "_onb"]:
                clean = basename.replace(suffix, "").replace("onboarding_", "").replace("onboarding-", "")
                matched_id = find_v1_account(OUTPUT_DIR, account_id=clean)
                if matched_id:
                    break

    if not matched_id:
        # Last resort: list all accounts and let user know
        accounts = list_accounts(OUTPUT_DIR)
        error_msg = (
            f"Could not find a matching v1 account for this onboarding transcript.\n"
            f"Available accounts: {accounts}\n"
            f"Use --account-id to specify the account explicitly."
        )
        print(f"  [ERROR] {error_msg}")
        return {"status": "error", "error": error_msg}

    account_id = matched_id
    print(f"  Matched account: {account_id}")

    # Load v1 memo
    v1_dir = get_output_dir(OUTPUT_DIR, account_id, "v1")
    v1_memo = load_json(os.path.join(v1_dir, "account_memo_v1.json"))
    company_name = v1_memo.get("company_name", "Unknown")
    print(f"  Company: {company_name}")

    # Step 3: Extract updates from onboarding
    print("\n[Step 3/8] Extracting updates from onboarding transcript...")
    updates = extract_onboarding_updates(transcript, v1_memo, llm)
    print(f"  Updates extracted: {len(updates)} fields")

    # Step 4: Apply updates to create v2 memo
    print("\n[Step 4/8] Applying updates to create v2 memo...")
    v2_memo = apply_updates(v1_memo, updates)
    v2_memo["account_id"] = account_id  # Ensure account_id stays the same

    # Step 5: Generate v2 Agent Spec
    print("\n[Step 5/8] Generating v2 Retell Agent Draft Spec...")
    v2_agent_spec = generate_agent_spec(v2_memo, version="v2")

    # Step 6: Generate changelog
    print("\n[Step 6/8] Generating changelog...")
    changelog = generate_changelog(v1_memo, v2_memo, account_id)
    changelog_md = changelog_to_markdown(changelog)
    print(f"  Changes detected: {changelog['total_changes']}")

    # Step 7: Save v2 outputs
    print("\n[Step 7/8] Saving v2 outputs...")
    v2_dir = get_output_dir(OUTPUT_DIR, account_id, "v2")
    save_json(v2_memo, os.path.join(v2_dir, "account_memo_v2.json"))
    save_json(v2_agent_spec, os.path.join(v2_dir, "agent_spec_v2.json"))
    save_json(changelog, os.path.join(v2_dir, "changelog.json"))

    # Save markdown changelog
    changelog_md_path = os.path.join(v2_dir, "changelog.md")
    with open(changelog_md_path, "w", encoding="utf-8") as f:
        f.write(changelog_md)
    print(f"  [SAVED] {changelog_md_path}")

    # Also save to the global changelog directory
    global_changelog_dir = os.path.join(os.path.dirname(OUTPUT_DIR), "changelog")
    ensure_dir(global_changelog_dir)
    global_md_path = os.path.join(global_changelog_dir, f"{account_id}_changelog.md")
    with open(global_md_path, "w", encoding="utf-8") as f:
        f.write(changelog_md)
    print(f"  [SAVED] {global_md_path}")

    # Save metadata
    metadata = {
        "source_file": os.path.basename(transcript_path),
        "source_path": transcript_path,
        "pipeline": "B",
        "version": "v2",
        "processed_at": timestamp(),
        "account_id": account_id,
        "company_name": company_name,
        "changes_count": changelog["total_changes"],
    }
    save_json(metadata, os.path.join(v2_dir, "metadata.json"))

    # Step 8: Update tracking task
    print("\n[Step 8/8] Updating tracking task...")
    if tracker:
        tracker.create_task(account_id, company_name, "v2", "pending_review")

    print(f"\n{'='*60}")
    print(f"  ✓ Pipeline B complete for: {company_name}")
    print(f"  ✓ Updates: {changelog['total_changes']} changes applied")
    print(f"  ✓ Outputs saved to: {v2_dir}")
    print(f"{'='*60}\n")

    return {
        "account_id": account_id,
        "company_name": company_name,
        "version": "v2",
        "output_dir": v2_dir,
        "changes_count": changelog["total_changes"],
        "status": "success",
    }


def run_batch():
    """
    Batch mode: Process all demo transcripts (Pipeline A), then all onboarding transcripts (Pipeline B).
    """
    print(f"\n{'#'*60}")
    print(f"  BATCH PROCESSING MODE")
    print(f"  Dataset directory: {DATASET_DIR}")
    print(f"{'#'*60}\n")

    llm = LLMClient()
    tracker = TaskTracker()

    demo_dir = os.path.join(DATASET_DIR, "demo")
    onboarding_dir = os.path.join(DATASET_DIR, "onboarding")

    results = {"demo": [], "onboarding": [], "errors": []}

    # Phase 1: Process all demo calls
    if os.path.exists(demo_dir):
        demo_files = sorted([
            f for f in os.listdir(demo_dir)
            if f.endswith((".txt", ".json", ".md", ".transcript"))
        ])
        print(f"\n[BATCH] Found {len(demo_files)} demo transcript(s)")

        for i, filename in enumerate(demo_files, 1):
            filepath = os.path.join(demo_dir, filename)
            print(f"\n--- Demo {i}/{len(demo_files)}: {filename} ---")
            try:
                result = pipeline_a_demo(filepath, llm, tracker)
                results["demo"].append(result)
            except Exception as e:
                error = {"file": filename, "pipeline": "A", "error": str(e)}
                results["errors"].append(error)
                print(f"  [ERROR] Failed: {e}")
                traceback.print_exc()
    else:
        print(f"  [WARN] Demo directory not found: {demo_dir}")

    # Phase 2: Process all onboarding calls
    if os.path.exists(onboarding_dir):
        onboarding_files = sorted([
            f for f in os.listdir(onboarding_dir)
            if f.endswith((".txt", ".json", ".md", ".transcript"))
        ])
        print(f"\n[BATCH] Found {len(onboarding_files)} onboarding transcript(s)")

        for i, filename in enumerate(onboarding_files, 1):
            filepath = os.path.join(onboarding_dir, filename)
            print(f"\n--- Onboarding {i}/{len(onboarding_files)}: {filename} ---")
            try:
                result = pipeline_b_onboarding(filepath, llm=llm, tracker=tracker)
                results["onboarding"].append(result)
            except Exception as e:
                error = {"file": filename, "pipeline": "B", "error": str(e)}
                results["errors"].append(error)
                print(f"  [ERROR] Failed: {e}")
                traceback.print_exc()
    else:
        print(f"  [WARN] Onboarding directory not found: {onboarding_dir}")

    # Summary
    print(f"\n{'#'*60}")
    print(f"  BATCH PROCESSING COMPLETE")
    print(f"{'#'*60}")
    print(f"  Demo calls processed:       {len(results['demo'])}")
    print(f"  Onboarding calls processed: {len(results['onboarding'])}")
    print(f"  Errors:                     {len(results['errors'])}")

    if results["errors"]:
        print(f"\n  ERRORS:")
        for err in results["errors"]:
            print(f"    - [{err['pipeline']}] {err['file']}: {err['error']}")

    # Save batch report
    report_path = os.path.join(OUTPUT_DIR, "batch_report.json")
    save_json(
        {
            "run_timestamp": timestamp(),
            "results": results,
            "summary": {
                "demo_processed": len(results["demo"]),
                "onboarding_processed": len(results["onboarding"]),
                "errors": len(results["errors"]),
                "total_files": len(results["demo"]) + len(results["onboarding"]),
            },
        },
        report_path,
    )

    return results


def list_all_accounts():
    """List all processed accounts and their versions."""
    accounts = list_accounts(OUTPUT_DIR)
    if not accounts:
        print("No accounts found. Run 'python run_pipeline.py batch' or process individual transcripts first.")
        return

    print(f"\n{'='*60}")
    print(f"  Processed Accounts ({len(accounts)} total)")
    print(f"{'='*60}\n")

    for acct_id in sorted(accounts):
        v1_exists = os.path.exists(get_output_dir(OUTPUT_DIR, acct_id, "v1"))
        v2_exists = os.path.exists(get_output_dir(OUTPUT_DIR, acct_id, "v2"))
        versions = []
        if v1_exists:
            versions.append("v1")
        if v2_exists:
            versions.append("v2")

        # Load company name from memo
        company = "Unknown"
        for v in ["v2", "v1"]:
            memo_path = os.path.join(get_output_dir(OUTPUT_DIR, acct_id, v), f"account_memo_{v}.json")
            if os.path.exists(memo_path):
                try:
                    memo = load_json(memo_path)
                    company = memo.get("company_name", "Unknown")
                except Exception:
                    pass
                break

        print(f"  {acct_id}")
        print(f"    Company:  {company}")
        print(f"    Versions: {', '.join(versions)}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Clara AI Automation Pipeline - Demo Call to Retell Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_pipeline.py demo --input dataset/demo/call1.txt
  python run_pipeline.py onboarding --input dataset/onboarding/call1.txt --account-id acme-plumbing
  python run_pipeline.py batch
  python run_pipeline.py list
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Pipeline command")

    # Demo command
    demo_parser = subparsers.add_parser("demo", help="Process a demo call transcript (Pipeline A)")
    demo_parser.add_argument("--input", "-i", required=True, help="Path to demo transcript file")

    # Onboarding command
    onb_parser = subparsers.add_parser("onboarding", help="Process an onboarding transcript (Pipeline B)")
    onb_parser.add_argument("--input", "-i", required=True, help="Path to onboarding transcript file")
    onb_parser.add_argument("--account-id", "-a", help="Account ID to update (auto-detected if not specified)")

    # Batch command
    subparsers.add_parser("batch", help="Batch process all files in dataset/")

    # List command
    subparsers.add_parser("list", help="List all processed accounts")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "demo":
        llm = LLMClient()
        tracker = TaskTracker()
        result = pipeline_a_demo(args.input, llm, tracker)
        if result["status"] != "success":
            sys.exit(1)

    elif args.command == "onboarding":
        llm = LLMClient()
        tracker = TaskTracker()
        result = pipeline_b_onboarding(args.input, account_id=args.account_id, llm=llm, tracker=tracker)
        if result["status"] != "success":
            sys.exit(1)

    elif args.command == "batch":
        results = run_batch()
        if results["errors"]:
            sys.exit(1)

    elif args.command == "list":
        list_all_accounts()


if __name__ == "__main__":
    main()

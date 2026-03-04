"""
task_tracker.py - Create and update task/tracking items for each account.

Supports:
- Local JSON file tracking (default, zero-cost)
- GitHub Issues (free, if you have a repo)
"""

import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
from scripts.utils import ensure_dir

load_dotenv()


class TaskTracker:
    """Manage task tracking items for accounts."""

    def __init__(self):
        tracker_type = os.getenv("TASK_TRACKER", "local_file").lower()
        self.output_dir = os.getenv("OUTPUT_DIR", "outputs")

        if tracker_type == "github_issues":
            self.tracker = GitHubIssuesTracker()
        else:
            self.tracker = LocalFileTracker(self.output_dir)

        print(f"  [TASKS] Using {tracker_type} tracker")

    def create_task(self, account_id: str, company_name: str, version: str, status: str = "pending_review") -> dict:
        """Create a new tracking task for an account."""
        return self.tracker.create_task(account_id, company_name, version, status)

    def update_task(self, account_id: str, updates: dict) -> dict:
        """Update an existing task."""
        return self.tracker.update_task(account_id, updates)

    def list_tasks(self) -> list:
        """List all tasks."""
        return self.tracker.list_tasks()


class LocalFileTracker:
    """Store tasks as JSON files locally."""

    def __init__(self, output_dir: str):
        self.tasks_dir = os.path.join(output_dir, "tasks")
        ensure_dir(self.tasks_dir)

    def create_task(self, account_id: str, company_name: str, version: str, status: str) -> dict:
        task = {
            "task_id": f"task-{account_id}-{version}",
            "account_id": account_id,
            "company_name": company_name,
            "version": version,
            "status": status,
            "title": f"[{version.upper()}] Review agent config for {company_name}",
            "description": f"Agent {version} has been auto-generated for {company_name} (account: {account_id}). "
                          f"Please review the agent spec and account memo before deploying.",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "checklist": [
                {"item": "Review account memo for accuracy", "done": False},
                {"item": "Review agent system prompt", "done": False},
                {"item": "Verify emergency routing rules", "done": False},
                {"item": "Test agent in Retell sandbox", "done": False},
                {"item": "Approve for deployment", "done": False},
            ],
        }

        filepath = os.path.join(self.tasks_dir, f"{account_id}_{version}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(task, f, indent=2)

        print(f"  [TASKS] Created task: {task['title']}")
        return task

    def update_task(self, account_id: str, updates: dict) -> dict:
        # Find latest task for this account
        for version in ["v2", "v1"]:
            filepath = os.path.join(self.tasks_dir, f"{account_id}_{version}.json")
            if os.path.exists(filepath):
                with open(filepath, "r") as f:
                    task = json.load(f)
                task.update(updates)
                task["updated_at"] = datetime.now().isoformat()
                with open(filepath, "w") as f:
                    json.dump(task, f, indent=2)
                print(f"  [TASKS] Updated task for {account_id}")
                return task

        print(f"  [TASKS] Warning: No existing task found for {account_id}")
        return {}

    def list_tasks(self) -> list:
        tasks = []
        if not os.path.exists(self.tasks_dir):
            return tasks
        for filename in os.listdir(self.tasks_dir):
            if filename.endswith(".json"):
                filepath = os.path.join(self.tasks_dir, filename)
                with open(filepath, "r") as f:
                    tasks.append(json.load(f))
        return tasks


class GitHubIssuesTracker:
    """Create GitHub Issues as tracking items."""

    def __init__(self):
        self.token = os.getenv("GITHUB_TOKEN", "")
        self.repo = os.getenv("GITHUB_REPO", "")
        if not self.token or not self.repo:
            raise ValueError(
                "GITHUB_TOKEN and GITHUB_REPO must be set in .env for GitHub Issues tracker. "
                "Or set TASK_TRACKER=local_file to use local file tracking."
            )
        self.api_base = f"https://api.github.com/repos/{self.repo}"
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def create_task(self, account_id: str, company_name: str, version: str, status: str) -> dict:
        title = f"[{version.upper()}] Review agent config for {company_name}"
        body = (
            f"## Agent Configuration Review\n\n"
            f"- **Account ID**: `{account_id}`\n"
            f"- **Company**: {company_name}\n"
            f"- **Version**: {version}\n"
            f"- **Status**: {status}\n\n"
            f"### Checklist\n"
            f"- [ ] Review account memo for accuracy\n"
            f"- [ ] Review agent system prompt\n"
            f"- [ ] Verify emergency routing rules\n"
            f"- [ ] Test agent in Retell sandbox\n"
            f"- [ ] Approve for deployment\n"
        )

        payload = {
            "title": title,
            "body": body,
            "labels": ["clara-pipeline", version, status],
        }

        response = requests.post(
            f"{self.api_base}/issues",
            json=payload,
            headers=self.headers,
            timeout=30,
        )
        response.raise_for_status()
        issue = response.json()
        print(f"  [TASKS] Created GitHub Issue #{issue['number']}: {title}")

        return {
            "task_id": f"github-issue-{issue['number']}",
            "account_id": account_id,
            "url": issue["html_url"],
            "number": issue["number"],
        }

    def update_task(self, account_id: str, updates: dict) -> dict:
        print(f"  [TASKS] GitHub Issues update not implemented for {account_id}")
        return {}

    def list_tasks(self) -> list:
        response = requests.get(
            f"{self.api_base}/issues",
            params={"labels": "clara-pipeline", "state": "all"},
            headers=self.headers,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

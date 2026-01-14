"""
Notion API helper functions.
"""

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

NOTION_API_VERSION = "2022-06-28"
NOTION_BASE_URL = "https://api.notion.com/v1"


@dataclass
class AssignmentData:
    """Data structure for an assignment."""

    course_name: str
    assignment_name: str
    project: str
    due: datetime | None
    reminder: datetime | None


class NotionHelper:
    """Helper class for Notion API operations."""

    def __init__(self):
        self.api_key = os.getenv("NOTION_API_KEY")
        if not self.api_key:
            raise ValueError("NOTION_API_KEY not found in environment variables")

        self.database_id = os.getenv("NOTION_DATABASE_ID")
        if not self.database_id:
            raise ValueError("NOTION_DATABASE_ID not found in environment variables")

        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": NOTION_API_VERSION,
            "Content-Type": "application/json",
        }
        self._http = httpx.Client(headers=self._headers, timeout=30.0)

    def _request(
        self, method: str, endpoint: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make a request to the Notion API."""
        url = f"{NOTION_BASE_URL}/{endpoint}"
        response = self._http.request(method, url, json=body)
        response.raise_for_status()
        return response.json()

    def _query_database(self, start_cursor: str | None = None) -> dict[str, Any]:
        """Query database."""
        body: dict[str, Any] = {}
        if start_cursor:
            body["start_cursor"] = start_cursor
        return self._request("POST", f"databases/{self.database_id}/query", body)

    def _retrieve_database(self) -> dict[str, Any]:
        """Retrieve database schema."""
        return self._request("GET", f"databases/{self.database_id}")

    def _update_database(self, properties: dict[str, Any]) -> dict[str, Any]:
        """Update database schema."""
        return self._request(
            "PATCH", f"databases/{self.database_id}", {"properties": properties}
        )

    def _create_page(self, properties: dict[str, Any]) -> dict[str, Any]:
        """Create a new page in the database."""
        return self._request(
            "POST",
            "pages",
            {"parent": {"database_id": self.database_id}, "properties": properties},
        )

    def _update_page(self, page_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        """Update a page."""
        return self._request("PATCH", f"pages/{page_id}", {"properties": properties})

    def get_existing_assignments(self) -> dict[str, dict[str, Any]]:
        """Fetch existing assignments from Notion database."""
        existing_assignments: dict[str, dict[str, Any]] = {}

        # Paginate through all results
        has_more = True
        start_cursor = None

        while has_more:
            response = self._query_database(start_cursor)
            results = response.get("results", [])

            for page in results:
                try:
                    name = page["properties"]["Name"]["title"][0]["plain_text"]
                    due_date = page["properties"]["Due"]["date"]
                    existing_assignments[name] = {
                        "id": page["id"],
                        "due": due_date["start"] if due_date else None,
                    }
                except (KeyError, IndexError, TypeError):
                    continue

            has_more = response.get("has_more", False)
            start_cursor = response.get("next_cursor")

        return existing_assignments

    def ensure_select_option_exists(
        self, property_name: str, option_name: str
    ) -> str | None:
        """Ensure a select option exists in the database schema."""
        db = self._retrieve_database()
        property_schema = db["properties"][property_name]

        # Check if option already exists
        for option in property_schema["select"]["options"]:
            if option["name"] == option_name:
                return option["id"]

        # Create new option
        try:
            # Extract only the fields Notion expects (id, name, color) to preserve existing options
            existing_options = [
                {k: v for k, v in opt.items() if k in ("id", "name", "color")}
                for opt in property_schema["select"]["options"]
            ]
            new_options = existing_options + [
                {"name": option_name, "color": "default"}
            ]
            updated_db = self._update_database(
                {property_name: {"select": {"options": new_options}}}
            )
            print(f"Created select option '{option_name}' for '{property_name}'")

            # Return the new option's ID
            for option in updated_db["properties"][property_name]["select"]["options"]:
                if option["name"] == option_name:
                    return option["id"]
        except httpx.HTTPStatusError as e:
            print(f"Error creating select option '{option_name}': {e}")

        return None

    def update_or_create_assignment(
        self,
        assignment: AssignmentData,
        existing_assignments: dict[str, dict[str, Any]],
    ) -> None:
        """Update an existing assignment or create a new one."""
        name = assignment.assignment_name
        due_date_str = assignment.due.strftime("%Y-%m-%d") if assignment.due else None
        reminder_date_str = (
            assignment.reminder.strftime("%Y-%m-%d") if assignment.reminder else None
        )

        if name in existing_assignments:
            # Update if deadline changed
            if existing_assignments[name]["due"] != due_date_str:
                page_id = existing_assignments[name]["id"]
                try:
                    self._update_page(
                        page_id,
                        {
                            "Due": {
                                "date": {"start": due_date_str}
                                if due_date_str
                                else None
                            }
                        },
                    )
                    print(f"Updated: {name}")
                except httpx.HTTPStatusError as e:
                    print(f"Error updating '{name}': {e}")
        else:
            # Create new assignment
            try:
                course_id = self.ensure_select_option_exists(
                    "Course", assignment.course_name
                )
                project_id = self.ensure_select_option_exists(
                    "Project", assignment.project
                )

                properties: dict[str, Any] = {
                    "Name": {"title": [{"text": {"content": name}}]},
                    "Status": {"status": {"name": "To-do"}},
                    "Due": {"date": {"start": due_date_str} if due_date_str else None},
                    "Reminder/Start/Unlock": {
                        "date": {"start": reminder_date_str}
                        if reminder_date_str
                        else None
                    },
                }

                if course_id:
                    properties["Course"] = {"select": {"id": course_id}}
                if project_id:
                    properties["Project"] = {"select": {"id": project_id}}

                self._create_page(properties)
                print(f"Created: {name}")
            except httpx.HTTPStatusError as e:
                print(f"Error creating '{name}': {e}")

    def import_assignments(self, assignments: list[AssignmentData]) -> None:
        """Import a list of assignments to Notion."""
        existing = self.get_existing_assignments()
        for assignment in assignments:
            self.update_or_create_assignment(assignment, existing)
        print(f"\nImported {len(assignments)} assignments to Notion.")

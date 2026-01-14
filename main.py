"""
PrairieLearn Scraper - Import PrairieLearn assignments to Notion.

Usage:
    python main.py [course_id]

Examples:
    python main.py cpsc221
    python main.py  # Interactive course selection
"""

import sys

import pandas as pd

from config import COURSES
from notion_helper import NotionHelper
from scraper import PrairieLearnScraper


def display_assignments(assignments: list) -> None:
    """Display scraped assignments in a table format."""
    if not assignments:
        print("No assignments found.")
        return

    data = [
        {
            "Name": a.assignment_name,
            "Project": a.project,
            "Due": a.due.strftime("%Y-%m-%d %H:%M") if a.due else "None",
            "Unlock": a.reminder.strftime("%Y-%m-%d %H:%M") if a.reminder else "None",
        }
        for a in assignments
    ]
    df = pd.DataFrame(data)
    print("\nScraped Assignments:")
    print(df.to_string(index=False))
    print(f"\nTotal: {len(assignments)} assignments")


def select_course() -> str:
    """Interactively select a course."""
    print("\nAvailable courses:")
    for i, (key, config) in enumerate(COURSES.items(), 1):
        print(f"  {i}. {key} - {config.course_name}")

    while True:
        choice = input("\nSelect course (number or id): ").strip().lower()

        # Try as number
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(COURSES):
                return list(COURSES.keys())[idx]
        except ValueError:
            pass

        # Try as course id
        if choice in COURSES:
            return choice

        print("Invalid selection. Try again.")


def confirm_import() -> bool:
    """Ask user to confirm import."""
    while True:
        response = input("\nImport to Notion? (yes/no): ").strip().lower()
        if response in ("yes", "y"):
            return True
        if response in ("no", "n"):
            return False
        print("Please enter 'yes' or 'no'.")


def main() -> None:
    """Main entry point."""
    # Get course selection
    if len(sys.argv) > 1:
        course_id = sys.argv[1].lower()
        if course_id not in COURSES:
            print(f"Unknown course: {course_id}")
            print(f"Available: {', '.join(COURSES.keys())}")
            sys.exit(1)
    else:
        course_id = select_course()

    config = COURSES[course_id]
    print(f"\nScraping: {config.course_name}")
    print(f"URL: {config.assessments_url}")

    # Scrape assignments
    scraper = PrairieLearnScraper()
    assignments = scraper.run(config)

    if not assignments:
        print("No assignments found. Check if you're enrolled in this course.")
        return

    # Display results
    display_assignments(assignments)

    # Confirm and import
    if confirm_import():
        notion = NotionHelper()
        notion.import_assignments(assignments)
        print("Import complete!")
    else:
        print("Import cancelled.")


if __name__ == "__main__":
    main()

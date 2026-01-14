"""
PrairieLearn scraper for UBC courses.
"""

import os
import re
import time
from datetime import datetime

import pytz
from bs4 import BeautifulSoup, Tag
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from config import CourseConfig
from notion_helper import AssignmentData

load_dotenv()

TIMEZONE = pytz.timezone("America/Vancouver")
LOGIN_URL = "https://us.prairielearn.com/pl/login"


class PrairieLearnScraper:
    """Scraper for PrairieLearn assessments."""

    def __init__(self):
        self.driver: webdriver.Chrome | None = None

    def _init_driver(self) -> None:
        """Initialize Chrome WebDriver."""
        self.driver = webdriver.Chrome()

    def _login(self) -> None:
        """Log in to PrairieLearn using UBC CWL."""
        if not self.driver:
            raise RuntimeError("Driver not initialized")

        username = os.getenv("PL_USERNAME")
        password = os.getenv("PL_PASSWORD")

        if not username or not password:
            raise ValueError("PL_USERNAME and PL_PASSWORD must be set in .env")

        self.driver.get(LOGIN_URL)
        time.sleep(1)

        # Click UBC login
        self.driver.find_element(
            By.LINK_TEXT, "University of British Columbia (ubc.ca)"
        ).click()

        # Wait for login form and enter credentials
        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.ID, "username"))
        )
        self.driver.find_element(By.ID, "username").send_keys(username)
        self.driver.find_element(By.ID, "password").send_keys(password)
        self.driver.find_element(By.NAME, "_eventId_proceed").click()

        # Wait for Duo 2FA approval and redirect to PrairieLearn
        print("\nWaiting for Duo 2FA approval...")
        WebDriverWait(self.driver, 120).until(EC.url_contains("prairielearn.com"))
        print("Login successful!")

    def _parse_date(self, date_str: str) -> datetime | None:
        """Parse a date string from PrairieLearn."""
        if not date_str or date_str == "—":
            return None

        # Clean timezone markers
        date_str = re.sub(r"\s*\(?(PST|PDT)\)?", "", date_str).strip()

        # Try parsing ISO format first (from popover)
        try:
            # Remove timezone offset suffix (e.g., "-08")
            if re.search(r"[+-]\d{2}$", date_str):
                date_str = date_str[:-3]
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            return TIMEZONE.localize(dt)
        except ValueError:
            pass

        # Try human-readable format (e.g., "23:59, Sat, Apr 25")
        try:
            # Parse with current year
            current_year = datetime.now().year
            dt = datetime.strptime(f"{date_str} {current_year}", "%H:%M, %a, %b %d %Y")
            return TIMEZONE.localize(dt)
        except ValueError:
            pass

        return None

    def _parse_available_credit(
        self, credit_text: str
    ) -> tuple[datetime | None, datetime | None]:
        """
        Parse the 'Available credit' column text.
        Returns (deadline, unlock_date).
        """
        deadline = None
        unlock_date = None

        if not credit_text or credit_text.strip() == "None":
            return None, None

        # Pattern: "100% until 23:59, Sat, Apr 25"
        until_match = re.search(r"(\d+%)\s+until\s+(.+)", credit_text)
        if until_match:
            deadline = self._parse_date(until_match.group(2))

        # Pattern: "100% starting from 08:00, Mon, Jan 19"
        starting_match = re.search(r"(\d+%)\s+starting from\s+(.+)", credit_text)
        if starting_match:
            unlock_date = self._parse_date(starting_match.group(2))

        return deadline, unlock_date

    def _scrape_from_popover(self, row: Tag) -> tuple[datetime | None, datetime | None]:
        """Try to extract deadline info from the popover button."""
        popover_button = row.find("button", class_="btn btn-xs btn-ghost")
        if not popover_button:
            return None, None

        popover_html = popover_button.get("data-bs-content")
        if not popover_html or not isinstance(popover_html, str):
            return None, None

        popover = BeautifulSoup(popover_html, "html.parser")
        deadline_rows = popover.find_all("tr")[1:]  # Skip header

        most_relevant = None
        unlock_date = None

        now = datetime.now(TIMEZONE)

        for row in deadline_rows:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            percentage = cells[0].text.strip()
            unlock_str = cells[1].text.strip()
            deadline_str = cells[2].text.strip()

            deadline = self._parse_date(deadline_str)
            parsed_unlock = self._parse_date(unlock_str)

            if parsed_unlock:
                unlock_date = parsed_unlock

            # Find earliest 100% deadline that hasn't passed
            if deadline and deadline >= now and percentage == "100%":
                if most_relevant is None or deadline < most_relevant:
                    most_relevant = deadline

        return most_relevant, unlock_date

    def scrape_course(self, config: CourseConfig) -> list[AssignmentData]:
        """Scrape all assessments for a course."""
        if not self.driver:
            raise RuntimeError("Driver not initialized")

        self.driver.get(config.assessments_url)
        time.sleep(2)  # Wait for page load

        html = self.driver.page_source
        soup = BeautifulSoup(html, "html.parser")

        assignments: list[AssignmentData] = []

        table = soup.find("table", attrs={"aria-label": "Assessments"})
        if not table:
            print("Assessments table not found")
            return assignments

        tbody = table.find("tbody")
        if not tbody:
            print("Table body not found")
            return assignments

        # Find project headers
        project_headers = tbody.find_all(
            "th", attrs={"data-testid": "assessment-group-heading"}
        )
        print(f"Found {len(project_headers)} assessment groups")

        for header in project_headers:
            project_name = header.text.strip()
            print(f"\nProcessing: {project_name}")

            parent_row = header.find_parent("tr")
            if not parent_row:
                continue

            # Process each assessment row under this project
            assessment_row = parent_row.find_next_sibling("tr")
            while assessment_row:
                # Check if we've hit the next project header
                if assessment_row.find(
                    "th", attrs={"data-testid": "assessment-group-heading"}
                ):
                    break

                name_cells = assessment_row.find_all("td", class_="align-middle")
                if len(name_cells) >= 2:
                    # Get assignment name
                    name_cell = name_cells[1]
                    link = name_cell.find("a")
                    name = link.text.strip() if link else name_cell.text.strip()

                    # Get credit/deadline info - try from third cell first
                    deadline = None
                    unlock_date = None

                    if len(name_cells) >= 3:
                        credit_text = name_cells[2].text.strip()
                        deadline, unlock_date = self._parse_available_credit(
                            credit_text
                        )

                    # If no deadline from text, try popover
                    if not deadline:
                        deadline, unlock_from_popover = self._scrape_from_popover(
                            assessment_row
                        )
                        if not unlock_date:
                            unlock_date = unlock_from_popover

                    # Create assignment name with project prefix
                    full_name = f"{project_name} - {name}"

                    assignment = AssignmentData(
                        course_name=config.course_name,
                        assignment_name=full_name,
                        project=project_name,
                        due=deadline,
                        reminder=unlock_date,
                    )
                    assignments.append(assignment)
                    print(f"  {name}: due={deadline}, unlock={unlock_date}")

                assessment_row = assessment_row.find_next_sibling("tr")

        return assignments

    def run(self, config: CourseConfig) -> list[AssignmentData]:
        """Run the scraper for a course."""
        try:
            self._init_driver()
            self._login()
            return self.scrape_course(config)
        finally:
            if self.driver:
                self.driver.quit()

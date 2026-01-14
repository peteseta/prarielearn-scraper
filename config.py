"""
Course configurations for PrairieLearn scraper.
"""

from dataclasses import dataclass


@dataclass
class CourseConfig:
    """Configuration for a PrairieLearn course."""

    course_id: str  # Short identifier (e.g., "cpsc221")
    course_name: str  # Display name for Notion
    assessments_url: str  # PrairieLearn assessments page URL


# Available courses
COURSES: dict[str, CourseConfig] = {
    "cpsc121": CourseConfig(
        course_id="cpsc121",
        course_name="CPSC_V 121 201/202/203 2024W2",
        assessments_url="https://us.prairielearn.com/pl/course_instance/169408/assessments",
    ),
    "cpsc210": CourseConfig(
        course_id="cpsc210",
        course_name="CPSC_V 210 201/202/203 2024W2",
        assessments_url="https://us.prairielearn.com/pl/course_instance/171718/assessments",
    ),
    "cpsc221": CourseConfig(
        course_id="cpsc221",
        course_name="CPSC_V 221 201/202/203 2025W2",
        assessments_url="https://us.prairielearn.com/pl/course_instance/202639/assessments",
    ),
}

"""Load internship listings exported from Apify as CSV."""

from __future__ import annotations

import csv
from pathlib import Path


class CsvScraper:
    """Read and normalize Apify Internshala CSV records."""

    def __init__(self, csv_path: str | Path = "data/dataset_internshala_scraper.csv") -> None:
        self._csv_path = Path(csv_path)

    def scraper(self) -> list[dict]:
        """Return normalized internship records."""

        if not self._csv_path.exists():
            raise FileNotFoundError(
                f"Internship CSV not found: {self._csv_path.resolve()}"
            )

        with self._csv_path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:
            rows = csv.DictReader(file)
            return [self._normalize_row(row) for row in rows]

    @staticmethod
    def _clean(value: str | None) -> str:
        return (value or "").strip()

    @classmethod
    def _normalize_row(cls, row: dict[str, str | None]) -> dict:

        skills = [
            cls._clean(row.get(f"skills/{index}"))
            for index in range(7)
        ]

        skills = [skill for skill in skills if skill]

        stipend = cls._clean(row.get("stipend/raw"))

        if not stipend:
            minimum = cls._clean(row.get("stipend/min"))
            maximum = cls._clean(row.get("stipend/max"))
            period = cls._clean(row.get("stipend/period"))

            if minimum and maximum:
                stipend = f"₹ {minimum} - {maximum}"

                if period:
                    stipend += f" /{period}"

            elif minimum:
                stipend = f"₹ {minimum}"

                if period:
                    stipend += f" /{period}"

        return {
            "title": cls._clean(row.get("title")),
            "company": cls._clean(row.get("company")),
            "description": cls._clean(row.get("description")),
            "skills_required": skills,
            "location": (
                cls._clean(row.get("locations/0"))
                or "Not specified"
            ),
            "apply_url": (
                cls._clean(row.get("applyUrl"))
                or cls._clean(row.get("url"))
            ),
            "source": "apify_internshala",
            "job_type": (
                cls._clean(row.get("recordType"))
                or "internship"
            ),
            "stipend": stipend,
            "duration": cls._format_duration(
                row.get("durationMonths")
            ),
        }

    @classmethod
    def _format_duration(cls, value: str | None) -> str:

        duration = cls._clean(value)

        if not duration:
            return ""

        try:
            number = float(duration)
        except ValueError:
            return duration

        number_text = (
            str(int(number))
            if number.is_integer()
            else str(number)
        )

        unit = "month" if number == 1 else "months"

        return f"{number_text} {unit}"
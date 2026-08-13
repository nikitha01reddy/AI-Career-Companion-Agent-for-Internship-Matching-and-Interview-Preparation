"""Tests for cover-letter extraction fallbacks."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.agents.cover_letter_agent import CoverLetterAgent
from app.schemas.user_detail import CoverLetterData


class TestCoverLetterAgent:
    """Heuristic recovery when PDF text extraction is noisy."""

    @pytest.mark.asyncio
    async def test_recovers_fields_from_noisy_pdf_text(self) -> None:
        client = AsyncMock()
        client.extract.return_value = CoverLetterData(
            salutation="Dear Hiring Manager,",
            signature="John Doe",
        )
        agent = CoverLetterAgent(client)
        noisy_text = (
            "JOHNDOE\n"
            "/envel⌢pejohn@johndoe.com/linkedin-inlinkedin.com/in/johndoe♂phone123.456.7890♂¶ap-¶arkerCity , ST\n"
            "August 12, 2026\n"
            "Hiring Manager\n"
            "Microsoft Corporation\n"
            "1 Microsoft Way\n"
            "Redmond, WA 98052\n"
            "Dear Hiring Manager,\n"
            "I am excited to apply for the Software Engineering Intern role at Microsoft. "
            "My experience building backend systems and AI applications has prepared me to contribute quickly. "
            "I have built APIs, automated workflows, and production-ready services using Python and FastAPI. "
            "I am especially drawn to Microsoft because of its engineering culture and product impact. "
            "Thank you for your time and consideration.\n"
            "Kind Regards,\n"
            "John Doe\n"
            "Applicant"
        )

        result = await agent.parse(noisy_text)

        assert result.applicant_name == "John Doe"
        assert result.email == "john@johndoe.com"
        assert result.phone_number == "123.456.7890"
        assert result.address == "City , ST"
        assert result.date == "August 12, 2026"
        assert result.hiring_manager_name == "Hiring Manager"
        assert result.company_name == "Microsoft Corporation"
        assert result.company_address == "1 Microsoft Way, Redmond, WA 98052"
        assert result.salutation == "Dear Hiring Manager,"
        assert result.opening_paragraph.startswith(
            "I am excited to apply for the Software Engineering Intern role at Microsoft."
        )
        assert "My experience building backend systems" in result.opening_paragraph
        assert result.body_paragraphs == [
            (
                "I have built APIs, automated workflows, and production-ready services using "
                "Python and FastAPI. I am especially drawn to Microsoft because of its "
                "engineering culture and product impact."
            )
        ]
        assert result.why_this_company == (
            "I have built APIs, automated workflows, and production-ready services using "
            "Python and FastAPI. I am especially drawn to Microsoft because of its "
            "engineering culture and product impact."
        )
        assert result.closing_paragraph == "Thank you for your time and consideration."
        assert result.signature == "John Doe"

    @pytest.mark.asyncio
    async def test_prefers_fallback_sections_when_llm_chunks_are_weaker(self) -> None:
        client = AsyncMock()
        client.extract.return_value = CoverLetterData(
            applicant_name="John Doe",
            email="john@johndoe.com",
            phone_number="123.456.7890",
            address="City , ST",
            date="August 12, 2026",
            hiring_manager_name="Hiring Manager",
            company_name="Microsoft Corporation",
            company_address="1 Microsoft Way, Redmond, WA 98052",
            salutation="Dear Hiring Manager,",
            opening_paragraph=(
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
                "Nunc aliquam ultrices aliquet. Cras ac placerat ex, non rhoncus tortor."
            ),
            body_paragraphs=[
                (
                    "Cras ac placerat ex, non rhoncus tortor. Phasellus accumsan sit amet "
                    "felis vitae varius."
                )
            ],
            closing_paragraph="Kind Regards,",
            signature="John Doe",
        )
        agent = CoverLetterAgent(client)
        text = (
            "JOHN DOE\n"
            "# john@johndoe.com ð linkedin.com/in/johndoe  123.456.7890 * City, ST\n"
            "August 12, 2026\n"
            "Hiring Manager\n"
            "Microsoft Corporation\n"
            "1 Microsoft Way\n"
            "Redmond, WA 98052\n"
            "Dear Hiring Manager,\n"
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Nunc aliquam ultrices aliquet.\n"
            "Cras ac placerat ex, non rhoncus tortor. Phasellus accumsan sit amet felis vitae varius.\n"
            "Nullam efficitur lorem nec orci scelerisque, commodo rutrum arcu varius. Nullam orci\n"
            "metus, rutrum sit amet enim sit amet, luctus rutrum metus. Vivamus commodo, quam a\n"
            "euismod venenatis, felis lorem porta massa, ac cursus massa nibh eu lectus. Duis pretium\n"
            "in elit nec sodales. Vivamus consectetur tristique ante eget ultricies. Cras sed lectus luctus,\n"
            "commodo urna fringilla, placerat urna.\n"
            "Aliquam ut ligula orci. Sed cursus interdum ante, et cursus erat aliquam vel. Maece-\n"
            "nas sodales ligula mattis condimentum convallis. Donec aliquet ut libero eget dignissim.\n"
            "Etiam gravida bibendum venenatis. Maecenas accumsan magna lectus. Mauris leo urna,\n"
            "tincidunt at eros vel, consequat varius urna. Curabitur blandit, nunc sed ultricies vehicula,\n"
            "neque turpis blandit massa, pulvinar ultrices orci ligula et enim. Morbi at efficitur ipsum.\n"
            "Aliquam ullamcorper consequat nunc, quis pulvinar orci facilisis sit amet. Pellentesque\n"
            "volutpat quam vitae luctus euismod.\n"
            "Fusce mauris enim, maximus in lorem mattis, volutpat euismod nibh. Class aptent\n"
            "taciti sociosqu ad litora torquent per conubia nostra, per inceptos himenaeos. Suspendisse\n"
            "ac leo cursus, bibendum justo eget, laoreet risus. In sodales nisl vel viverra fringilla. Ut\n"
            "venenatis nisl id dapibus mollis. In elit tellus, venenatis sit amet lacinia in, cursus id erat.\n"
            "In hac habitasse platea dictumst. Pellentesque pharetra risus eu ex luctus bibendum. Proin\n"
            "dictum neque sit amet mauris viverra, et hendrerit lacus elementum.\n"
            "Kind Regards,\n"
            "John Doe\n"
            "Applicant\n"
        )

        result = await agent.parse(text)

        assert result.opening_paragraph == (
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Nunc aliquam ultrices aliquet."
        )
        assert result.body_paragraphs == [
            (
                "Cras ac placerat ex, non rhoncus tortor. Phasellus accumsan sit amet felis vitae "
                "varius. Nullam efficitur lorem nec orci scelerisque, commodo rutrum arcu varius. "
                "Nullam orci metus, rutrum sit amet enim sit amet, luctus rutrum metus. Vivamus "
                "commodo, quam a euismod venenatis, felis lorem porta massa, ac cursus massa nibh "
                "eu lectus. Duis pretium in elit nec sodales. Vivamus consectetur tristique ante "
                "eget ultricies. Cras sed lectus luctus, commodo urna fringilla, placerat urna."
            ),
            (
                "Aliquam ut ligula orci. Sed cursus interdum ante, et cursus erat aliquam vel. "
                "Maecenas sodales ligula mattis condimentum convallis. Donec aliquet ut libero eget "
                "dignissim. Etiam gravida bibendum venenatis. Maecenas accumsan magna lectus. "
                "Mauris leo urna, tincidunt at eros vel, consequat varius urna. Curabitur blandit, "
                "nunc sed ultricies vehicula, neque turpis blandit massa, pulvinar ultrices orci "
                "ligula et enim. Morbi at efficitur ipsum. Aliquam ullamcorper consequat nunc, "
                "quis pulvinar orci facilisis sit amet. Pellentesque volutpat quam vitae luctus euismod."
            ),
            (
                "Fusce mauris enim, maximus in lorem mattis, volutpat euismod nibh. Class aptent "
                "taciti sociosqu ad litora torquent per conubia nostra, per inceptos himenaeos. "
                "Suspendisse ac leo cursus, bibendum justo eget, laoreet risus. In sodales nisl vel "
                "viverra fringilla. Ut venenatis nisl id dapibus mollis. In elit tellus, venenatis "
                "sit amet lacinia in, cursus id erat. In hac habitasse platea dictumst. Pellentesque "
                "pharetra risus eu ex luctus bibendum. Proin dictum neque sit amet mauris viverra, "
                "et hendrerit lacus elementum."
            ),
        ]
        assert result.closing_paragraph == ""

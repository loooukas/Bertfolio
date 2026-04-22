from __future__ import annotations

import re

from finbert_site.normalizer import deterministic_document_from_text


def _name_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def test_deterministic_canonical_speaker_merges_middle_initial_aliases() -> None:
    content = """
Timothy D. Cook: Good afternoon and welcome to our earnings call.
Operator: We will now begin the question-and-answer session.
Ben Reitzes: Thanks for taking my question on demand trends?
Timothy Cook: Thanks, Ben. Demand remained strong this quarter.
Aaron Christopher Rakers: Could you talk about margins and guidance?
Aaron Rakers: Quick follow-up on pricing?
"""

    document = deterministic_document_from_text(
        ticker="AAPL",
        company_name="Apple Inc.",
        source="motley_fool",
        source_url="https://example.com/aapl",
        title="Apple Transcript",
        published_date="2026-01-29",
        content=content,
        extraction_confidence=0.88,
        parsing_warnings=[],
        participants=[
            {"name": "Timothy Cook", "role": "Chief Executive Officer"},
            {"name": "Ben Reitzes", "role": "Analyst"},
            {"name": "Aaron Rakers", "role": "Analyst"},
        ],
        management_roster=[{"name": "Timothy Cook", "title": "Chief Executive Officer"}],
    )

    tim_speakers = {section.speaker for section in document.sections if "cook" in _name_key(section.speaker)}
    aaron_speakers = {section.speaker for section in document.sections if "rakers" in _name_key(section.speaker)}
    assert len(tim_speakers) == 1
    assert len(aaron_speakers) == 1


def test_deterministic_section_typing_marks_apple_analyst_blocks_as_qa() -> None:
    content = """
Timothy D. Cook: We delivered record iPhone revenue and expanded gross margin in most regions.
Operator: We will now take questions.
Ben Reitzes: Thanks for taking my question. How should we think about AI demand in enterprise?
Timothy Cook: Thanks Ben. We remain confident in demand and continue to invest.
"""

    document = deterministic_document_from_text(
        ticker="AAPL",
        company_name="Apple Inc.",
        source="motley_fool",
        source_url="https://example.com/aapl",
        title="Apple Transcript",
        published_date="2026-01-29",
        content=content,
        extraction_confidence=0.9,
        parsing_warnings=[],
        participants=[
            {"name": "Timothy Cook", "role": "Chief Executive Officer"},
            {"name": "Ben Reitzes", "role": "Analyst"},
        ],
        management_roster=[{"name": "Timothy Cook", "title": "Chief Executive Officer"}],
    )

    by_speaker = {(section.speaker, section.order_index): section for section in document.sections}
    ben = [section for section in document.sections if _name_key(section.speaker) == "ben reitzes"][0]
    tim_opening = [section for section in document.sections if "cook" in _name_key(section.speaker)][0]
    tim_answer = [section for section in document.sections if "cook" in _name_key(section.speaker)][1]

    assert tim_opening.section_type == "prepared_remarks"
    assert ben.section_type == "qa"
    assert tim_answer.section_type == "qa"
    assert ben.speaker_role == "analyst"
    assert tim_opening.speaker_role == "management"
    assert by_speaker


def test_deterministic_tesla_qa_flow_detects_host_operator_and_closing() -> None:
    content = """
Elon Musk: Thanks everyone for joining. We delivered strong unit growth and improved margins.
Travis Axelrod: Thank you. We will now begin the question-and-answer session. Operator, please go ahead.
Operator: The next question comes from Dan Levy with Barclays.
Dan Levy: Thanks for taking my question. How should we think about gross margin next quarter?
Elon Musk: Thanks Dan. We continue to expect gradual margin expansion.
Operator: That is unfortunately all the time we have for Q&A today.
Elon Musk: Thanks everyone for joining today.
"""

    document = deterministic_document_from_text(
        ticker="TSLA",
        company_name="Tesla Inc.",
        source="motley_fool",
        source_url="https://example.com/tsla",
        title="Tesla Transcript",
        published_date="2026-01-29",
        content=content,
        extraction_confidence=0.93,
        parsing_warnings=[],
        participants=[
            {"name": "Elon Musk", "role": "Chief Executive Officer"},
            {"name": "Travis Axelrod", "role": "Head of Investor Relations"},
            {"name": "Dan Levy", "role": "Analyst"},
        ],
        management_roster=[{"name": "Elon Musk", "title": "Chief Executive Officer"}],
    )

    lookup = {(section.speaker, section.text): section for section in document.sections}
    host = next(section for section in document.sections if _name_key(section.speaker) == "travis axelrod")
    operator_next_question = next(
        section for section in document.sections if "next question comes from dan levy" in section.text.lower()
    )
    dan = next(section for section in document.sections if _name_key(section.speaker) == "dan levy")
    management_answer = [
        section
        for section in document.sections
        if _name_key(section.speaker) == "elon musk" and "continue to expect gradual margin expansion" in section.text.lower()
    ][0]
    qa_closing = next(section for section in document.sections if "all the time we have for q&a" in section.text.lower())

    assert host.speaker_role == "host_ir"
    assert host.section_type == "qa"
    assert operator_next_question.section_type == "qa"
    assert dan.speaker_role == "analyst"
    assert dan.section_type == "qa"
    assert management_answer.speaker_role == "management"
    assert management_answer.section_type == "qa"
    assert qa_closing.section_type == "other"
    assert lookup


def test_deterministic_role_resolution_leaves_no_null_for_obvious_speakers() -> None:
    content = """
Kevan Parekh: Welcome everyone. We delivered strong services revenue.
Operator: The next question comes from Samik Chatterjee.
Samik Chatterjee: Thanks for taking my question. How should we think about iPhone demand?
Kevan Parekh: We remain confident and continue to invest.
"""

    document = deterministic_document_from_text(
        ticker="AAPL",
        company_name="Apple Inc.",
        source="motley_fool",
        source_url="https://example.com/aapl",
        title="Apple Transcript",
        published_date="2026-01-29",
        content=content,
        extraction_confidence=0.91,
        parsing_warnings=[],
        participants=[
            {"name": "Kevan Parekh", "role": "Chief Financial Officer"},
            {"name": "Samik Chatterjee", "role": "Analyst"},
        ],
        management_roster=[{"name": "Kevan Parekh", "title": "Chief Financial Officer"}],
    )

    obvious_speakers = [section for section in document.sections if _name_key(section.speaker) in {"kevan parekh", "operator", "samik chatterjee"}]
    assert obvious_speakers
    assert all(section.speaker_role for section in obvious_speakers)


def test_yahoo_roster_enrichment_marks_management_without_participant_titles() -> None:
    content = """
Timothy D. Cook: We had a strong quarter and exceeded guidance.
Operator: We will now take questions.
Ben Reitzes: Thanks for taking my question on margins?
Timothy Cook: We remain focused on execution.
"""

    document = deterministic_document_from_text(
        ticker="AAPL",
        company_name="Apple Inc.",
        source="motley_fool",
        source_url="https://example.com/aapl",
        title="Apple Transcript",
        published_date="2026-01-29",
        content=content,
        extraction_confidence=0.87,
        parsing_warnings=[],
        participants=[
            {"name": "Ben Reitzes", "role": "Analyst"},
        ],
        management_roster=[{"name": "Timothy Cook", "title": "Chief Executive Officer"}],
    )

    tim_sections = [section for section in document.sections if "cook" in _name_key(section.speaker)]
    ben_section = next(section for section in document.sections if _name_key(section.speaker) == "ben reitzes")
    assert tim_sections
    assert all(section.speaker_role == "management" for section in tim_sections)
    assert ben_section.speaker_role == "analyst"

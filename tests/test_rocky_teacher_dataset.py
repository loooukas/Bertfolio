from __future__ import annotations

from rocky.build_teacher_dataset import _flatten_document, _infer_year_quarter, _parse_published_date, _skip_flags


def test_skip_flags_marks_operator_fluff() -> None:
    should_skip, is_short, is_operator_like, reasons = _skip_flags(
        speaker="Operator",
        speaker_role="operator",
        section_type="qa",
        text="Our next question comes from the line of Jane Doe. Please go ahead.",
        char_count=68,
        word_count=14,
    )
    assert should_skip is True
    assert is_short is True
    assert is_operator_like is True
    assert "operator_or_host_fluff" in reasons


def test_flatten_document_preserves_adjacency_fields() -> None:
    document = {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "source_url": "https://example.com/transcript",
        "published_date": "2026-01-29",
        "normalization_mode": "deterministic_degraded",
        "participants": [
            {"name": "Operator", "role": "operator"},
            {"name": "Tim Cook", "role": "management"},
            {"name": "Ben Reitzes", "role": "analyst"},
        ],
        "sections": [
            {
                "speaker": "Operator",
                "speaker_role": "operator",
                "section_type": "prepared_remarks",
                "text": "Welcome to the call.",
                "order_index": 0,
                "evidence_snippets": [],
            },
            {
                "speaker": "Ben Reitzes",
                "speaker_role": "analyst",
                "section_type": "qa",
                "text": "How should we think about demand next quarter?",
                "order_index": 1,
                "evidence_snippets": ["How should we think about demand next quarter?"],
            },
            {
                "speaker": "Tim Cook",
                "speaker_role": "management",
                "section_type": "qa",
                "text": "We continue to expect strong demand and margin expansion.",
                "order_index": 2,
                "evidence_snippets": ["We continue to expect strong demand and margin expansion."],
            },
        ],
    }

    rows = _flatten_document(
        transcript_id="AAPL_2026q1_deadbeef0001",
        transcript_quarter="2026-Q1",
        document_dict=document,
    )

    assert len(rows) == 3
    assert rows[1]["previous_speaker"] == "Operator"
    assert rows[1]["next_speaker"] == "Tim Cook"
    assert rows[1]["transcript_has_qa"] is True
    assert rows[2]["metadata"]["adjacent_sample_ids"]["previous_sample_id"] is not None


def test_parse_published_date_handles_kaggle_style_timestamp() -> None:
    out = _parse_published_date("Aug 27, 2020, 9:00 p.m. ET")
    assert out == "2020-08-27"


def test_infer_year_quarter_prefers_q_label() -> None:
    year, quarter = _infer_year_quarter("2021-Q3", "2021-08-05")
    assert (year, quarter) == (2021, 3)

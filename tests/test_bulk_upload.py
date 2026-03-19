"""
Tests for BulkUploadService._parse_csv

_parse_csv is a pure sync method — it only reads from a ZipFile in memory,
so no Telegram, no DB, no async required.
"""

import io
import zipfile

import pytest

from tgbot.services.bulk_upload import BulkUploadService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_zip(csv_content: str) -> zipfile.ZipFile:
    """Returns an in-memory ZipFile containing questions.csv."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("questions.csv", csv_content)
    buf.seek(0)
    return zipfile.ZipFile(buf, "r")


def _service() -> BulkUploadService:
    """Returns a BulkUploadService with None dependencies (only _parse_csv is called)."""
    return BulkUploadService(bot=None, repo=None, config=None)  # type: ignore[arg-type]


_CSV_HEADER = "subject,year,session,q_number,q_type,answer,images,options\n"


# ===========================================================================
# Choice questions
# ===========================================================================

class TestParseCsvChoice:
    def test_single_choice_row(self):
        csv = _CSV_HEADER + "math,2024,main,1,choice,А,q1.jpg,5\n"
        rows = _service()._parse_csv(_make_zip(csv))
        assert len(rows) == 1
        r = rows[0]
        assert r["subject"] == "math"
        assert r["year"] == 2024
        assert r["session"] == "main"
        assert r["q_number"] == 1
        assert r["q_type"] == "choice"
        assert r["correct_answer"]["answer"] == "А"
        assert r["correct_answer"]["options"] == "5"

    def test_choice_images_split_by_comma(self):
        csv = _CSV_HEADER + "math,2024,main,1,choice,А,\"q1.jpg,q2.jpg\",5\n"
        rows = _service()._parse_csv(_make_zip(csv))
        assert rows[0]["images"] == ["q1.jpg", "q2.jpg"]

    def test_choice_answer_uppercased(self):
        csv = _CSV_HEADER + "math,2024,main,1,choice,а,q1.jpg,5\n"
        rows = _service()._parse_csv(_make_zip(csv))
        assert rows[0]["correct_answer"]["answer"] == "А"

    def test_multiple_rows(self):
        csv = (
            _CSV_HEADER
            + "math,2024,main,1,choice,А,q1.jpg,5\n"
            + "math,2024,main,2,choice,Б,q2.jpg,5\n"
        )
        rows = _service()._parse_csv(_make_zip(csv))
        assert len(rows) == 2
        assert rows[1]["q_number"] == 2

    def test_empty_images_field(self):
        csv = _CSV_HEADER + "math,2024,main,1,choice,А,,5\n"
        rows = _service()._parse_csv(_make_zip(csv))
        assert rows[0]["images"] == []


# ===========================================================================
# Short questions
# ===========================================================================

class TestParseCsvShort:
    def test_short_answer_stored_as_is(self):
        csv = _CSV_HEADER + "physics,2024,main,3,short,4.5,q3.jpg,-\n"
        rows = _service()._parse_csv(_make_zip(csv))
        r = rows[0]
        assert r["q_type"] == "short"
        assert r["correct_answer"]["answer"] == "4.5"

    def test_short_integer_answer(self):
        csv = _CSV_HEADER + "math,2024,main,5,short,42,q5.jpg,-\n"
        rows = _service()._parse_csv(_make_zip(csv))
        assert rows[0]["correct_answer"]["answer"] == "42"


# ===========================================================================
# Match questions
# ===========================================================================

class TestParseCsvMatch:
    def test_match_pairs_parsed(self):
        # Format: "1-А;2-Б;3-Д"
        csv = _CSV_HEADER + "physics,2024,main,2,match,1-А;2-Б;3-Д,q2.jpg,3x5\n"
        rows = _service()._parse_csv(_make_zip(csv))
        r = rows[0]
        assert r["q_type"] == "match"
        pairs = r["correct_answer"]["pairs"]
        assert pairs["1"] == "А"
        assert pairs["2"] == "Б"
        assert pairs["3"] == "Д"

    def test_match_options_stored(self):
        csv = _CSV_HEADER + "physics,2024,main,2,match,1-А;2-Б,q2.jpg,3x5\n"
        rows = _service()._parse_csv(_make_zip(csv))
        assert rows[0]["correct_answer"]["options"] == "3x5"

    def test_match_pair_letters_uppercased(self):
        csv = _CSV_HEADER + "physics,2024,main,2,match,1-а;2-б,q2.jpg,3x5\n"
        rows = _service()._parse_csv(_make_zip(csv))
        pairs = rows[0]["correct_answer"]["pairs"]
        assert pairs["1"] == "А"
        assert pairs["2"] == "Б"

    def test_match_only_first_pair_when_no_semicolons(self):
        # Parser splits on ";". Without semicolons, only the first match is extracted.
        csv = _CSV_HEADER + "math,2024,main,2,match,1А 2Б 3В,q2.jpg,3x5\n"
        rows = _service()._parse_csv(_make_zip(csv))
        pairs = rows[0]["correct_answer"]["pairs"]
        # Without semicolons the regex only finds the first digit-letter pair
        assert "1" in pairs


# ===========================================================================
# BOM handling and whitespace
# ===========================================================================

class TestParseCsvEdgeCases:
    def test_bom_header_handled(self):
        """Excel-exported CSVs often start with a UTF-8 BOM (\ufeff)."""
        csv = "\ufeff" + _CSV_HEADER + "math,2024,main,1,choice,А,q1.jpg,5\n"
        rows = _service()._parse_csv(_make_zip(csv))
        assert len(rows) == 1
        assert rows[0]["subject"] == "math"

    def test_subject_lowercased(self):
        csv = _CSV_HEADER + "MATH,2024,main,1,choice,А,q1.jpg,5\n"
        rows = _service()._parse_csv(_make_zip(csv))
        assert rows[0]["subject"] == "math"

    def test_q_type_lowercased(self):
        csv = _CSV_HEADER + "math,2024,main,1,CHOICE,А,q1.jpg,5\n"
        rows = _service()._parse_csv(_make_zip(csv))
        assert rows[0]["q_type"] == "choice"

    def test_whitespace_stripped_from_image_names(self):
        csv = _CSV_HEADER + "math,2024,main,1,choice,А,\" q1.jpg , q2.jpg \",5\n"
        rows = _service()._parse_csv(_make_zip(csv))
        assert "q1.jpg" in rows[0]["images"]
        assert "q2.jpg" in rows[0]["images"]

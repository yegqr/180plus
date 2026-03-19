"""
Tests for pure static helpers in infrastructure/database/repo/questions.py.
"""

from infrastructure.database.repo.questions import QuestionRepo


class _MockQuestion:
    """Minimal stand-in for the Question ORM model."""
    def __init__(self, image_file_id=None, images=None):
        self.image_file_id = image_file_id
        self.images = images or []
        self.q_type = None
        self.correct_answer = {}
        self.weight = 0


class TestUpdateQuestionFields:
    def test_appends_new_images(self):
        q = _MockQuestion(images=["old_id"])
        QuestionRepo._update_question_fields(q, ["new_id"], "choice", {}, 1)
        assert "old_id" in q.images
        assert "new_id" in q.images

    def test_no_duplicates_on_reupload(self):
        q = _MockQuestion(images=["id1"])
        QuestionRepo._update_question_fields(q, ["id1", "id1"], "choice", {}, 1)
        assert q.images.count("id1") == 1

    def test_sets_primary_image_when_absent(self):
        q = _MockQuestion(image_file_id=None, images=[])
        QuestionRepo._update_question_fields(q, ["first_id"], "choice", {}, 1)
        assert q.image_file_id == "first_id"

    def test_preserves_existing_primary_image(self):
        q = _MockQuestion(image_file_id="original", images=["original"])
        QuestionRepo._update_question_fields(q, ["new_id"], "choice", {}, 1)
        assert q.image_file_id == "original"

    def test_updates_q_type(self):
        q = _MockQuestion()
        QuestionRepo._update_question_fields(q, [], "match", {}, 3)
        assert q.q_type == "match"

    def test_updates_correct_answer(self):
        q = _MockQuestion()
        ca = {"pairs": {"1": "А"}}
        QuestionRepo._update_question_fields(q, [], "match", ca, 1)
        assert q.correct_answer == ca

    def test_updates_weight(self):
        q = _MockQuestion()
        QuestionRepo._update_question_fields(q, [], "match", {}, 4)
        assert q.weight == 4

    def test_empty_new_images_leaves_existing_unchanged(self):
        q = _MockQuestion(image_file_id="id1", images=["id1"])
        QuestionRepo._update_question_fields(q, [], "choice", {}, 1)
        assert q.images == ["id1"]
        assert q.image_file_id == "id1"

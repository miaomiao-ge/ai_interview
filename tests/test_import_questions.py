from types import SimpleNamespace

from openpyxl import Workbook

from tools import import_questions


class FakeSession:
    def __init__(self):
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def query(self, model):
        raise AssertionError("query should be monkeypatched through find_existing_question")

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def write_question_workbook(path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["问题类型", "序号", "题目（中文）", "题目（English）"])
    sheet.append(["个人基本情况与留学动机", 1, "请介绍自己。", "Please introduce yourself."])
    sheet.append([None, 2, "为什么选择西电？", "Why Xidian?"])
    workbook.save(path)


def test_read_questions_from_excel_carries_forward_category(tmp_path):
    path = tmp_path / "questions.xlsx"
    write_question_workbook(path)

    rows = import_questions.read_questions_from_excel(path)

    assert len(rows) == 2
    assert rows[0].category == "个人基本情况与留学动机"
    assert rows[0].question_no == 1
    assert rows[0].content_en == "Please introduce yourself."
    assert rows[1].category == "个人基本情况与留学动机"
    assert rows[1].question_no == 2


def test_upsert_questions_updates_existing_without_duplicate(monkeypatch):
    session = FakeSession()
    existing = SimpleNamespace(
        question_no=1,
        content="旧题目",
        content_en="Old question",
        source_hash="old",
    )
    row = import_questions.QuestionRow(
        category="综合素质",
        question_no=1,
        content="新题目",
        content_en="New question",
        source_file="questions.xlsx",
        source_row=2,
        source_hash="new-hash",
    )

    monkeypatch.setattr(import_questions, "SessionLocal", lambda: session)
    monkeypatch.setattr(import_questions, "find_existing_question", lambda db, item: existing)

    stats = import_questions.upsert_questions([row])

    assert stats.updated == 1
    assert stats.created == 0
    assert session.added == []
    assert existing.content == "新题目"
    assert existing.content_en == "New question"
    assert existing.source_hash == "new-hash"
    assert session.commits == 1
    assert session.closed is True

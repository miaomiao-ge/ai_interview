from types import SimpleNamespace

from tools.backfill_platform_accounts import plan_backfill


def user(**overrides):
    data = {"platform_user_id": None, "passport_no": "", "platform_account": ""}
    data.update(overrides)
    return SimpleNamespace(**data)


def test_matches_by_platform_user_id_first():
    updates, stats = plan_backfill(
        [user(platform_user_id=7, passport_no="OLD")],
        {"7": {"a@example.com"}},
        {"OLD": {"other@example.com"}},
    )
    assert updates[0][1] == "a@example.com"
    assert stats["matched_by_user_id"] == 1
    assert stats["matched_by_passport"] == 0


def test_falls_back_to_single_passport_match():
    updates, stats = plan_backfill(
        [user(platform_user_id=99, passport_no="p123456")],
        {},
        {"P123456": {"student@example.com"}},
    )
    assert updates[0][1] == "student@example.com"
    assert stats["matched_by_passport"] == 1


def test_ambiguous_passport_is_skipped():
    updates, stats = plan_backfill(
        [user(passport_no="P123456")],
        {},
        {"P123456": {"dev@example.com", "prod@example.com"}},
    )
    assert updates == []
    assert stats["ambiguous_passport"] == 1


def test_unmatched_user_is_counted():
    updates, stats = plan_backfill([user(passport_no="UNKNOWN")], {}, {})
    assert updates == []
    assert stats["unmatched"] == 1

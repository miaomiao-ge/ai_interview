from core.assessment import load_instrument, score_answers, validate_answers


def _all_zero():
    return {no: 0 for no in range(1, 54)}


def test_instrument_has_53_items_and_5_scale_points():
    instrument = load_instrument()

    assert instrument["instrument"] == "BSI-53"
    assert len(instrument["items"]) == 53
    assert [point["value"] for point in instrument["scale"]] == [0, 1, 2, 3, 4]
    assert instrument["items"][0]["no"] == 1


def test_validate_requires_all_53_answers():
    answers = _all_zero()
    answers.pop(7)

    assert validate_answers(answers) == "All 53 items must be answered"


def test_validate_rejects_out_of_range():
    answers = _all_zero()
    answers[12] = 5

    assert validate_answers(answers) == "Each answer must be within 0-4"


def test_validate_accepts_complete_answers():
    assert validate_answers(_all_zero()) is None


def test_all_zero_scores_are_neutral():
    result = score_answers(_all_zero())

    assert result["gsi"] == 0.0
    assert result["pst"] == 0
    assert result["psdi"] == 0.0
    assert result["risk_level"] == "NONE"
    assert result["risk_items"] == []
    assert set(result["dimensions"]) == {
        "SOM", "OC", "IS", "DEP", "ANX", "HOS", "PHOB", "PAR", "PSY"
    }


def test_dimension_and_index_formulas_match_platform():
    answers = _all_zero()
    answers[2] = 4
    answers[1] = 2
    answers[53] = 1
    answers[9] = 1

    result = score_answers(answers)

    assert result["dimensions"]["SOM"] == round(4 / 7, 3)
    assert result["dimensions"]["ANX"] == round(2 / 6, 3)
    assert result["dimensions"]["PSY"] == round(1 / 5, 3)
    assert result["pst"] == 4
    assert result["gsi"] == round(8 / 53, 3)
    assert result["psdi"] == 2.0
    assert result["risk_level"] == "WATCH"
    assert result["risk_items"] == [{"no": 9, "value": 1}]


def test_self_harm_item_escalates_to_urgent():
    answers = _all_zero()
    answers[9] = 2

    result = score_answers(answers)

    assert result["risk_level"] == "URGENT"
    assert result["risk_items"] == [{"no": 9, "value": 2}]


def test_hostility_items_trigger_watch_at_three():
    answers = _all_zero()
    answers[40] = 3
    answers[41] = 2

    result = score_answers(answers)

    assert result["risk_level"] == "WATCH"
    assert result["risk_items"] == [{"no": 40, "value": 3}]

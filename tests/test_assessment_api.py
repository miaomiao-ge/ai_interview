from core.assessment import load_instrument


def test_instrument_payload_localizes_text():
    from routers.assessment_api import build_instrument_view

    view = build_instrument_view("en")

    assert view["instrument"] == "BSI-53"
    assert view["items"][0]["text"].startswith("Nervousness")
    assert len(view["items"]) == 53


def test_instrument_payload_falls_back_to_zh_for_unknown_locale():
    from routers.assessment_api import build_instrument_view

    view = build_instrument_view("fr")

    assert view["items"][0]["text"] == load_instrument()["items"][0]["zh"]

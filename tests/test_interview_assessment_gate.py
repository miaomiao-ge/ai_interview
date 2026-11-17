def test_assessment_gate_response_shape():
    from routers.user_api import assessment_required_response

    payload = assessment_required_response()

    assert payload["status"] == "error"
    assert payload["code"] == "assessment_required"
    assert "心理测评" in payload["message"]

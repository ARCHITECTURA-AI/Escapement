from escapement_engine.schemas.actions import Action, Malformed, parse_action, tool_schemas


def test_valid_actions():
    assert parse_action({"tool": "review_journal"}) == Action("review_journal", {})
    a = parse_action({"tool": "interact", "arguments": {"target_id": "x", "operation": "enter_code", "value": "123"}})
    assert isinstance(a, Action) and a.arguments["value"] == "123"


def test_rejections_are_malformed_and_stable():
    cases = [
        ("not a dict", "Request must be an object"),
        ({"tool": "smash"}, "Unknown tool"),
        ({"tool": "inspect", "arguments": {}}, "Missing argument 'target_id'"),
        ({"tool": "inspect", "arguments": {"target_id": "A B"}}, "must be an id"),
        ({"tool": "inspect", "arguments": {"target_id": 3}}, "must be a string"),
        ({"tool": "inspect", "arguments": {"target_id": "x", "force": "y"}}, "Unexpected argument 'force'"),
        ({"tool": "interact", "arguments": {"target_id": "x", "operation": "smash"}}, "Unsupported operation"),
        ({"tool": "interact", "arguments": {"target_id": "x", "operation": "enter_code"}}, "needs a 'value'"),
        ({"tool": "interact", "arguments": {"target_id": "x", "operation": "open", "value": "1"}}, "Only enter_code"),
        ({"tool": "interact", "arguments": {"target_id": "x", "operation": "enter_code", "value": "12a"}}, "1 to 12 digits"),
        ({"tool": "move", "arguments": {"destination_id": "x"}, "claim": "I escaped"}, "Unexpected field 'claim'"),
    ]
    for request, fragment in cases:
        out = parse_action(request)
        assert isinstance(out, Malformed), request
        assert fragment in out.message, (request, out.message)


def test_tool_schemas_cover_all_tools():
    names = {t["name"] for t in tool_schemas()}
    assert names == {"inspect", "take", "use", "interact", "move", "review_journal"}

from scripts.conversation_probe import evaluate_turn, render_report


def _trace(core: str, response: str):
    return {
        "ok": True,
        "response": response,
        "thinker": {
            "status": "ready",
            "analysis": "Krótka analiza celu użytkownika.",
            "reply_core": core,
        },
    }


def test_evaluator_detects_preserved_question_and_forbidden_phrases():
    turn = {
        "text": "Jutro może pójdę na randkę.",
        "expect": {"forbidden": ["trzymam kciuki"], "required_any": ["z kim"]},
    }
    checks = evaluate_turn(turn, _trace("O, randka? Z kim się umówiłeś?", "O, randka? Z kim się umówiłeś?"))
    assert all(check["passed"] for check in checks)

    failed = evaluate_turn(turn, _trace("O, randka? Z kim się umówiłeś?", "Trzymam kciuki za jutro."))
    by_name = {check["name"]: check["passed"] for check in failed}
    assert by_name["question_preserved"] is False
    assert by_name["forbidden:trzymam kciuki"] is False
    assert by_name["required_any"] is False


def test_report_contains_brief_response_and_check_result():
    turn = {"text": "Dokończę przykład.", "expect": {}}
    trace = _trace("Jasne, dokończ.", "Jasne, dokończ.")
    checks = evaluate_turn(turn, trace)
    report = render_report(
        {"name": "smoke"},
        [{"turn": turn, "trace": trace, "checks": checks}],
    )
    assert "# Conversation probe — smoke" in report
    assert "**Reply core:** Jasne, dokończ." in report
    assert "**Monika:** Jasne, dokończ." in report
    assert "PASS" in report

import json

from scripts.conversation_probe import (
    compare_with_baseline,
    evaluate_conversation,
    evaluate_turn,
    render_report,
    write_jsonl,
)


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
    assert by_name["question_core_overlap"] is False
    assert by_name["forbidden:trzymam kciuki"] is False
    assert by_name["required_any"] is False


def test_evaluator_rejects_a_different_question_about_the_same_user_turn():
    core = (
        "Ile zyskasz na tej przesiadce w porównaniu do kosztów i "
        "ewentualnych ograniczeń płyty głównej?"
    )
    paraphrase_of_user = (
        "Zastanawiasz się, czy upgrade procesora w ramach tej samej architektury "
        "da wystarczający wzrost wydajności, czy warto wymienić wszystko naraz?"
    )
    checks = evaluate_turn(
        {"text": "Rozważam upgrade procesora.", "expect": {}},
        _trace(core, paraphrase_of_user),
    )
    by_name = {check["name"]: check["passed"] for check in checks}
    assert by_name["question_preserved"] is True
    assert by_name["question_core_overlap"] is False
    assert by_name["core_overlap"] is False


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


def test_character_quality_checks_detect_psychologizing_and_question_pressure():
    turn = {
        "text": "Po prostu zawsze jestem skupiony.",
        "expect": {
            "reject_unsupported_traits": True,
            "allow_memory_claim": False,
            "must_not_ask": True,
            "max_sentences": 2,
        },
    }
    response = (
        "Masz w sobie naturalną zdolność, to cenna cecha. "
        "Zapiszę to. Co cię rozprasza?"
    )

    checks = evaluate_turn(turn, _trace(response, response))
    failed = {
        check["name"]
        for check in checks
        if not check["passed"]
    }

    assert "must_not_ask" in failed
    assert "no_memory_claim" in failed
    assert "unsupported_trait:naturalna_zdolnosc" in failed
    assert "unsupported_trait:cenna_cecha" in failed


def test_conversation_checks_measure_question_runs_and_repetition():
    scenario = {
        "conversation_expect": {
            "max_total_questions": 1,
            "max_consecutive_question_turns": 1,
            "max_adjacent_similarity": 0.5,
        }
    }
    results = [
        {
            "trace": {"response": "Co pomaga ci się skupić?"},
            "checks": [],
        },
        {
            "trace": {"response": "Co pomaga ci się skupić?"},
            "checks": [],
        },
    ]

    checks = evaluate_conversation(scenario, results)
    by_name = {check["name"]: check["passed"] for check in checks}

    assert by_name["total_questions"] is False
    assert by_name["question_pressure"] is False
    assert by_name["adjacent_repetition"] is False


def test_jsonl_trace_is_versioned_and_redacts_secrets(tmp_path):
    scenario_path = tmp_path / "scenario.json"
    scenario_path.write_text(
        json.dumps({"schema_version": 2, "name": "quality"}),
        encoding="utf-8",
    )
    output = tmp_path / "trace.jsonl"
    result = {
        "turn": {"text": "Hej", "expect": {}},
        "trace": {
            "response": "Hej.",
            "api_key": "secret-value",
            "thinker": {"author_model": "model-a"},
        },
        "checks": [{"name": "live_response", "passed": True, "detail": ""}],
        "roundtrip_ms": 125.5,
    }

    write_jsonl(
        output,
        scenario={"schema_version": 2, "name": "quality"},
        scenario_path=scenario_path,
        results=[result],
        conversation_checks=[],
    )
    records = [
        json.loads(line)
        for line in output.read_text(encoding="utf-8").splitlines()
    ]

    assert records[0]["schema_version"] == 2
    assert len(records[0]["scenario_sha256"]) == 64
    assert records[1]["trace"]["api_key"] == "[REDACTED]"
    assert records[1]["roundtrip_ms"] == 125.5
    assert records[-1]["record_type"] == "conversation_summary"


def test_baseline_comparison_reports_pass_delta(tmp_path):
    baseline = tmp_path / "baseline.jsonl"
    baseline.write_text(
        "\n".join(
            [
                json.dumps({"record_type": "turn", "checks": [
                    {"name": "a", "passed": True},
                    {"name": "b", "passed": False},
                ]}),
                json.dumps({"record_type": "conversation_summary", "checks": []}),
            ]
        ),
        encoding="utf-8",
    )
    current = [
        {
            "checks": [
                {"name": "a", "passed": True},
                {"name": "b", "passed": True},
            ]
        }
    ]

    comparison = compare_with_baseline(baseline, current, [])

    assert comparison["baseline_passed"] == 1
    assert comparison["current_passed"] == 2
    assert comparison["delta"] == 1

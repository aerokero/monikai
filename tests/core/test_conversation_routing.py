from backend.conversation.routing import requires_capability_runtime


def test_casual_conversation_goes_to_text_author():
    assert not requires_capability_runtime(
        "W sumie nie wiem, po prostu zawsze jestem skupiony."
    )
    assert not requires_capability_runtime("Co o tym sądzisz?")


def test_operational_requests_stay_in_capability_runtime():
    assert requires_capability_runtime("Ustaw mi przypomnienie na jutro.")
    assert requires_capability_runtime("Przypomnij mi o raporcie za 10 minut.")
    assert requires_capability_runtime("Sprawdź pogodę w Warszawie.")
    assert requires_capability_runtime("Open this file for me.")


def test_external_context_always_uses_capability_runtime():
    assert requires_capability_runtime(
        "Co widzisz?",
        has_external_context=True,
    )


def test_spotify_read_request_is_operational_but_casual_mention_is_not():
    assert requires_capability_runtime("Co teraz leci na Spotify?")
    assert requires_capability_runtime("Pokaż moje playlisty Spotify.")
    assert not requires_capability_runtime("Lubię Spotify.")


def test_smart_home_requests_are_operational_but_casual_mention_is_not():
    assert requires_capability_runtime("Pokaż wszystkie urządzenia smart home.")
    assert requires_capability_runtime("Włącz lampę w salonie.")
    assert not requires_capability_runtime("Lubię tę lampę.")

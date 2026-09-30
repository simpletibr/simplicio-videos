from simplicio_video.words import map_words


def test_proportional_without_stt():
    w = map_words("aa bbbb", 1.2, None)
    assert [x["w"] for x in w] == ["aa", "bbbb"]
    assert w[0]["t"] == 0.0 and w[1]["t"] == 0.4 and w[1]["end"] == 1.2


def test_char_timeline_maps_misrecognised_words_onto_contract_text():
    # "Lothus Odontologia" recognised as "lotos ou dontologia": times still follow the letters
    rec = [{"w": "com", "start": 0.0, "end": 0.4}, {"w": "lotos", "start": 0.4, "end": 0.9},
           {"w": "ou", "start": 0.9, "end": 1.0}, {"w": "dontologia", "start": 1.0, "end": 1.8}]
    w = map_words("Com Lothus Odontologia.", 1.9, rec)
    assert [x["w"] for x in w] == ["Com", "Lothus", "Odontologia."]
    assert w[0]["t"] == 0.0 and 0.35 <= w[1]["t"] <= 0.45 and 0.85 <= w[2]["t"] <= 1.0
    assert w[-1]["end"] <= 1.8 + 1e-9

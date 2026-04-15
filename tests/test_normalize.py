from gca.pipeline.normalize import extract_normalized


def test_extract_steam_basic():
    payload = {
        "steam_appid": 730,
        "name": "Counter-Strike 2",
        "short_description": "tac shooter",
        "genres": [{"description": "Action"}, {"description": "FPS"}],
        "categories": [{"description": "Multi-player"}],
        "type": "game",
    }
    g = extract_normalized("steam", payload)
    assert g.platform == "steam"
    assert g.external_id == "730"
    assert g.title == "Counter-Strike 2"
    assert g.description == "tac shooter"
    assert "Action" in g.raw_tags
    assert "Multi-player" in g.raw_tags


def test_extract_steam_missing_id():
    g = extract_normalized("steam", {"name": "X"})
    assert g.external_id == ""


def test_extract_steam_empty_genres():
    g = extract_normalized("steam", {"steam_appid": 1, "name": "Y"})
    assert g.raw_tags == []


def test_extract_playstore():
    payload = {"appId": "com.foo", "title": "Foo", "description": "bar", "genre": "RPG"}
    g = extract_normalized("playstore", payload)
    assert g.platform == "playstore"
    assert g.external_id == "com.foo"
    assert g.title == "Foo"
    assert "RPG" in g.raw_tags


def test_extract_appstore():
    payload = {
        "trackId": 12345,
        "trackName": "AppName",
        "description": "desc",
        "genres": ["Games", "Action"],
    }
    g = extract_normalized("appstore", payload)
    assert g.external_id == "12345"
    assert g.title == "AppName"
    assert g.raw_tags == ["Games", "Action"]


def test_extract_unknown_platform():
    import pytest
    with pytest.raises(ValueError):
        extract_normalized("xbox", {})

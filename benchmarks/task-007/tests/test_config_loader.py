from config_loader import DEFAULT_CONFIG, load_config


def test_returns_defaults():
    assert load_config() == {
        "timeout": 30,
        "retries": 3,
        "debug": False,
    }


def test_overrides_do_not_change_defaults():
    config = load_config({"timeout": 5})

    assert config["timeout"] == 5
    assert load_config()["timeout"] == 30
    assert DEFAULT_CONFIG["timeout"] == 30


def test_returned_configs_are_independent():
    first = load_config()
    first["timeout"] = 1

    second = load_config()

    assert second["timeout"] == 30


def test_input_overrides_are_not_modified():
    overrides = {"debug": True}

    load_config(overrides)

    assert overrides == {"debug": True}

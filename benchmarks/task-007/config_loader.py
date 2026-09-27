DEFAULT_CONFIG = {
    "timeout": 30,
    "retries": 3,
    "debug": False,
}


def load_config(overrides=None):
    """Return an independent configuration dictionary."""
    config = dict(DEFAULT_CONFIG)

    if overrides:
        config.update(overrides)

    return config

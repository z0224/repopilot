from access_control import can_access


def test_active_admin_can_access():
    assert can_access("admin") is True


def test_active_editor_can_access():
    assert can_access("editor") is True


def test_viewer_cannot_access():
    assert can_access("viewer") is False


def test_inactive_admin_cannot_access():
    assert can_access("admin", is_active=False) is False


def test_unknown_role_cannot_access():
    assert can_access("unknown") is False

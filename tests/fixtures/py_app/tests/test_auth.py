import pytest

from app.services.auth import Session, check_password, login_user


def test_check_password():
    assert check_password("a", "a")


def test_login_requires_email():
    with pytest.raises(ValueError):
        login_user("", "x")


def test_session_refresh():
    assert Session("u").refresh()

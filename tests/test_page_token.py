"""Token tài khoản được đổi sang token của Page trước khi đăng video."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shopeetool import facebook  # noqa: E402


class Resp:
    def __init__(self, payload, code=200):
        self.status_code = code
        self._payload = payload

    def json(self):
        return self._payload


def test_user_token_is_swapped_for_the_selected_page():
    def fake_get(url, params=None, timeout=None):
        if url.endswith("/me"):
            return Resp({"id": "user-1", "name": "Tài khoản"})
        if url.endswith("/me/accounts"):
            return Resp({"data": [
                {"id": "other", "name": "Page khác", "access_token": "OTHER"},
                {"id": "1405", "name": "Biethaychua - Fan", "access_token": "PAGE"},
            ]})
        raise AssertionError(url)

    original = facebook.requests.get
    facebook.requests.get = fake_get
    try:
        token, name = facebook.resolve_page_token("USER", "1405", "v21.0")
    finally:
        facebook.requests.get = original
    assert token == "PAGE"
    assert name == "Biethaychua - Fan"


def test_page_token_is_kept():
    def fake_get(url, params=None, timeout=None):
        assert url.endswith("/me")
        return Resp({"id": "1405", "name": "Biethaychua - Fan"})

    original = facebook.requests.get
    facebook.requests.get = fake_get
    try:
        token, name = facebook.resolve_page_token("PAGE", "1405", "v21.0")
    finally:
        facebook.requests.get = original
    assert token == "PAGE"
    assert name == "Biethaychua - Fan"


if __name__ == "__main__":
    test_user_token_is_swapped_for_the_selected_page()
    test_page_token_is_kept()
    print("ok")

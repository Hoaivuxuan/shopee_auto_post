"""Comment nhóm không được gắn sẵn một câu mở cứng."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shopeetool import fb_group  # noqa: E402


def test_comment_draft_is_not_prefixed_with_the_stiff_opener():
    seen = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({
                "response": "Nồi này nấu vừa miệng nhà mình, hộp cơm mang đi vẫn ấm. 🤍 LINKHERE",
            }).encode()

    def capture(req, timeout=None):
        seen["prompt"] = json.loads(req.data.decode())["prompt"]
        seen["timeout"] = timeout
        return Resp()

    original = fb_group.urllib.request.urlopen
    fb_group.urllib.request.urlopen = capture
    try:
        draft = fb_group._draft_comment("Vợ nấu cơm, nồi 350.000₫.", "Nồi cơm điện 99k", "89.000 ₫")
    finally:
        fb_group.urllib.request.urlopen = original
    assert "Mình cũng gặp vụ này" not in seen["prompt"]
    assert "Đúng chủ đề" in seen["prompt"]
    assert "350.000" not in seen["prompt"]
    assert "99k" not in seen["prompt"].casefold()
    assert "89.000" not in seen["prompt"]
    assert "LINKHERE" in seen["prompt"]
    assert not fb_group._draft_ok("Nồi này chỉ 350.000₫ mà nấu rất vừa. 🤍 LINKHERE")
    assert fb_group.comment_text("Giá đỡ điện thoại 99k", "https://s.shopee.vn/abc").startswith("Giá đỡ điện thoại\n")
    assert draft.startswith(("🤍 ", "🌿 ", "🌸 ", "☁️ "))
    assert "Nồi này nấu vừa miệng" in draft
    assert fb_group._draft_ok(draft)
    assert not fb_group._draft_ok("Mình cũng gặp vụ này. Nồi nấu nhanh. LINKHERE")


if __name__ == "__main__":
    test_comment_draft_is_not_prefixed_with_the_stiff_opener()
    print("ok")

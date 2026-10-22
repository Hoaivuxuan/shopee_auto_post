import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shopeetool.fb_group import MAX_POST_LIMIT, clamp_post_limit


def test_blank_limit_uses_default():
    assert clamp_post_limit(None) == 10
    assert clamp_post_limit("") == 10
    assert clamp_post_limit(0) == 10


def test_typed_limit_is_kept_up_to_the_cap():
    assert clamp_post_limit(1) == 1
    assert clamp_post_limit("25") == 25
    assert clamp_post_limit(MAX_POST_LIMIT + 40) == MAX_POST_LIMIT

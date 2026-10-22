VERSION = "1.0.0"
APP_TITLE = "Shopee → Facebook Tool"


def __getattr__(name):
    if name == "get_affiliate_products":
        from .shopee_affiliate import get_affiliate_products
        return get_affiliate_products
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

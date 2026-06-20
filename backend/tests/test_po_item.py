from app.services.vendor_po_parser import zero_pad_item


def test_zero_pad_basic():
    assert zero_pad_item("1") == "00001"
    assert zero_pad_item("00001") == "00001"
    assert zero_pad_item("123") == "00123"


def test_zero_pad_strips_nondigits():
    assert zero_pad_item("1 2 3") == "00123"
    assert zero_pad_item("item 42") == "00042"


def test_zero_pad_empty():
    assert zero_pad_item("") == ""
    assert zero_pad_item(None) == ""


def test_zero_pad_custom_width():
    assert zero_pad_item("7", width=3) == "007"

from app.services.vendor_po_parser import parse_vendor_ids, zero_pad_item


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


def test_material_captures_slash_suffix():
    # "/ NN" eki varsa malzemeye dahil edilmeli (Item 6)
    ids = parse_vendor_ids("Malzeme: AB50K26 (NUK) / 50\n")
    assert ids.material is not None
    assert "/ 50" in ids.material.replace("  ", " ") or "/50" in ids.material.replace(" ", "")


def test_material_without_slash_suffix_still_matches():
    ids = parse_vendor_ids("Malzeme: AB50K26 (NUK)\n")
    assert ids.material is not None
    assert "AB50K26" in ids.material.replace(" ", "")
    assert "/" not in ids.material

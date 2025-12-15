from pathlib import Path


def test_lookup_returns_none_when_missing(tmp_path: Path):
    from grocery.tools import library

    products_path = tmp_path / "products.json"
    assert library.lookup(products_path, "milk") is None


def test_add_mapping_creates_and_then_lookup_finds(tmp_path: Path):
    from grocery.tools import library

    products_path = tmp_path / "products.json"
    library.add_mapping(
        products_path,
        item_name="milk",
        product={"display_name": "Hy-Vee Vitamin D Milk", "url": "u", "product_id": "p"},
        original_request="MILK",
    )
    found = library.lookup(products_path, "milk")
    assert found is not None
    assert found["display_name"] == "Hy-Vee Vitamin D Milk"
    assert "MILK" in found["original_requests"]


def test_verify_all_mapped_partitions(tmp_path: Path):
    from grocery.tools import library

    products_path = tmp_path / "products.json"
    library.add_mapping(
        products_path,
        item_name="milk",
        product={"display_name": "Hy-Vee Vitamin D Milk"},
        original_request="milk",
    )

    mapped, unmapped = library.verify_all_mapped(products_path, ["milk", "bread"])
    assert mapped == ["milk"]
    assert unmapped == ["bread"]



"""read_csv_preview: a file's columns and its first row, for the mapping pages
(phase 7 spec section 4.1)."""

from shopify_tool.csv_utils import read_csv_preview


def _write(tmp_path, text, encoding="utf-8"):
    path = tmp_path / "orders.csv"
    path.write_text(text, encoding=encoding)
    return str(path)


def test_it_returns_the_columns_in_file_order_and_the_first_row(tmp_path):
    path = _write(tmp_path, "Name,Lineitem sku,Qty\n#1001,ABC-1,2\n#1002,XYZ-9,1\n")
    assert read_csv_preview(path) == (
        ["Name", "Lineitem sku", "Qty"],
        {"Name": "#1001", "Lineitem sku": "ABC-1", "Qty": "2"},
    )


def test_it_detects_a_semicolon_file(tmp_path):
    path = _write(tmp_path, "Артикул;Наличност\nABC-1;40\nXYZ-9;3\n")
    assert read_csv_preview(path) == (
        ["Артикул", "Наличност"],
        {"Артикул": "ABC-1", "Наличност": "40"},
    )


def test_it_detects_a_tab_file(tmp_path):
    path = _write(tmp_path, "Sku\tAvailable\nABC-1\t40\nXYZ-9\t3\n")
    headers, first = read_csv_preview(path)
    assert headers == ["Sku", "Available"]
    assert first == {"Sku": "ABC-1", "Available": "40"}


def test_values_stay_text_and_an_empty_cell_is_an_empty_string(tmp_path):
    """A SKU of 00123 must not turn into 123, nor an empty cell into nan."""
    path = _write(tmp_path, "Sku,Note,Stock\n00123,,7\n00124,x,8\n")
    assert read_csv_preview(path)[1] == {"Sku": "00123", "Note": "", "Stock": "7"}


def test_a_file_with_no_rows_has_columns_and_no_first_row(tmp_path):
    path = _write(tmp_path, "Name,Lineitem sku\n")
    assert read_csv_preview(path) == (["Name", "Lineitem sku"], {})


def test_a_byte_order_mark_is_not_part_of_the_first_column(tmp_path):
    path = _write(tmp_path, "Name,Qty\n#1,2\n#2,3\n", encoding="utf-8-sig")
    assert read_csv_preview(path)[0] == ["Name", "Qty"]

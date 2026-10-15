from shared import i18n_check as c


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_python_keys(tmp_path):
    src = _write(tmp_path, "a.py", (
        'from shared.i18n import _, _n, N_\n'
        'X = N_("Saved.")\n'
        'def f(n, name):\n'
        '    label.setText(_("Save"))\n'
        '    _n("{n} order", "{n} orders", n)\n'
        '    _(name)\n'
    ))
    assert c.python_keys([src]) == {"Saved.": False, "Save": False, "{n} order": True}


def test_html_keys_collapse_whitespace(tmp_path):
    page = _write(tmp_path, "p.html", (
        '<button data-i18n>  Start\n   packing </button>'
        '<input data-i18n-attr="placeholder,title" placeholder="Search" title="Find a SKU">'
        '<p data-i18n>Ready &amp; waiting</p>'
    ))
    assert c.html_keys([page]) == {
        "Start packing": False, "Search": False, "Find a SKU": False, "Ready & waiting": False,
    }


def test_js_keys(tmp_path):
    js = _write(tmp_path, "p.js", (
        'el.textContent = t("Save");\n'
        "x = t('Close', {a: 1});\n"
        'y = tn("{n} order", "{n} orders", n);\n'
        'z = format("Save");\n'
    ))
    assert c.js_keys([js]) == {"Save": False, "Close": False, "{n} order": True}


def test_bare_python_literals(tmp_path):
    src = _write(tmp_path, "a.py", (
        'label.setText("Save")\n'
        'label.setText(_("Save"))\n'
        'QLabel("Name:", self)\n'
        'button.setToolTip(f"Open {name}")\n'
        'label.setText("")\n'
        'label.setText("—")\n'
        'ConfirmDialog(self, title="Delete?", body=_("Gone."), verb=_("Delete"))\n'
        'label.setText("Fulfilment Tool")\n'
        'QMessageBox.warning(self, "Oops", _("Bad"))\n'
        'toast(self, "Saved")\n'
    ))
    found = c.bare_python_literals([src], allow={"Fulfilment Tool"})
    assert found == [
        f"{src}:1: Save",
        f"{src}:3: Name:",
        f"{src}:4: Open {{name}}",
        f"{src}:7: Delete?",
        f"{src}:9: Oops",
        f"{src}:10: Saved",
    ]


def test_bare_html_text(tmp_path):
    page = _write(tmp_path, "p.html", (
        '<html><head><title>Logs</title><style>a{}</style></head><body>'
        '<h1 data-i18n>Logs</h1><p>Loose text</p><span>12</span>'
        '<script>var a = "x";</script></body></html>'
    ))
    assert c.bare_html_text([page], allow=set()) == [f"{page}:1: Loose text"]


def test_bare_js_literals(tmp_path):
    js = _write(tmp_path, "p.js", (
        'a.textContent = "Saved";\n'
        'a.textContent = t("Saved");\n'
        'a.title = "Open";\n'
        'a.placeholder = \'Search\';\n'
        'a.setAttribute("aria-label", "Close");\n'
        'a.className = "row";\n'
        'a.textContent = "";\n'
    ))
    assert c.bare_js_literals([js], allow=set()) == [
        f"{js}:1: Saved", f"{js}:3: Open", f"{js}:4: Search", f"{js}:5: Close",
    ]


def test_placeholders():
    assert c.placeholders("{n} of {m} labels") == {"n", "m"}
    assert c.placeholders("No fields") == set()


def test_files_skip_pycache(tmp_path):
    (tmp_path / "__pycache__").mkdir()
    _write(tmp_path, "a.py", "")
    (tmp_path / "__pycache__" / "b.py").write_text("", encoding="utf-8")
    assert c.files(tmp_path, "*.py") == [tmp_path / "a.py"]

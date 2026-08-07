"""Regression test for gui_main.py's frozen-Windows WeasyPrint/fontconfig
runtime setup -- no test previously covered DLL-directory selection or
FONTCONFIG_PATH resolution (CodeRabbit review on PR #259).
"""
import os
import sys
from pathlib import Path

import gui_main


def test_frozen_weasyprint_env_adds_gtk_dlls_dir(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/fake/App.exe", raising=False)
    calls = []
    monkeypatch.setattr(os, "add_dll_directory", lambda p: calls.append(p), raising=False)

    gui_main.configure_frozen_weasyprint_env()

    assert calls == [str(Path("/fake/App.exe").parent / "gtk-dlls")]


def test_frozen_weasyprint_env_noop_when_not_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    calls = []
    monkeypatch.setattr(os, "add_dll_directory", lambda p: calls.append(p), raising=False)

    gui_main.configure_frozen_weasyprint_env()

    assert calls == []


def test_fontconfig_env_prefers_bundled_frozen_candidate(monkeypatch, tmp_path):
    bundled = tmp_path / "gtk-dlls" / "etc" / "fonts"
    bundled.mkdir(parents=True)
    (bundled / "fonts.conf").write_text("")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "App.exe"), raising=False)
    monkeypatch.delenv("FONTCONFIG_PATH", raising=False)

    gui_main.configure_windows_fontconfig_env()

    assert os.environ["FONTCONFIG_PATH"] == str(bundled)


def test_fontconfig_env_skips_candidates_missing_fonts_conf(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(
        gui_main, "_WINDOWS_GTK3_FONTCONFIG_CANDIDATES", (str(tmp_path / "nowhere"),)
    )
    monkeypatch.delenv("FONTCONFIG_PATH", raising=False)

    gui_main.configure_windows_fontconfig_env()

    assert "FONTCONFIG_PATH" not in os.environ


def test_fontconfig_env_never_overrides_existing_value(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("FONTCONFIG_PATH", "/already/set")

    gui_main.configure_windows_fontconfig_env()

    assert os.environ["FONTCONFIG_PATH"] == "/already/set"


def test_fontconfig_env_noop_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("FONTCONFIG_PATH", raising=False)

    gui_main.configure_windows_fontconfig_env()

    assert "FONTCONFIG_PATH" not in os.environ

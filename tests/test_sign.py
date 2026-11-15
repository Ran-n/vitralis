#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/15 14:24:49.867204
Revised: 2026/11/15 14:24:49.867204

``vitralis-sign``: a generated key signs something the updater accepts; the key can be piped in; keygen never
overwrites a file; files that aren't this version's are refused; wrong inputs give a reason and exit 1.
"""

import io

import pytest
from blake3 import blake3

from tests.updates.fakes import OTHER_SECRET, PUBLIC, SECRET
from vitralis import sign as tool
from vitralis.updates.rules import parse_version
from vitralis.updates.signature import public_key, statement, verify

VERSION = "1.4.0"
ASSET = f"vitralis-{VERSION}-windows-x86_64.exe"


@pytest.fixture(autouse=True)
def this_checkout(monkeypatch):
    monkeypatch.setattr(tool, "current_version", lambda: parse_version(VERSION))


@pytest.fixture
def asset(tmp_path):
    path = tmp_path / ASSET
    path.write_bytes(b"MZ the exe")
    return path


def test_keygen_writes_a_new_key_and_prints_its_public_half(tmp_path, capsys):
    where = tmp_path / "key.txt"
    assert tool.main(["keygen", str(where)]) == 0
    secret = where.read_text(encoding="utf-8").strip()
    assert capsys.readouterr().out.strip() == public_key(secret)
    assert tool.main(["public", str(where)]) == 0
    assert capsys.readouterr().out.strip() == public_key(secret)


def test_keygen_never_overwrites_a_file(tmp_path, capsys):
    where = tmp_path / "key.txt"
    where.write_text("my only copy", encoding="utf-8")
    assert tool.main(["keygen", str(where)]) == 1
    assert where.read_text(encoding="utf-8") == "my only copy"
    assert "couldn't be created" in capsys.readouterr().err


def test_a_signed_asset_is_what_the_updater_accepts(tmp_path, asset, capsys):
    key = tmp_path / "key.txt"
    key.write_text(SECRET + "\n", encoding="utf-8")
    assert tool.main(["sign", str(key), str(asset)]) == 0
    signature = (tmp_path / (ASSET + ".sig")).read_text(encoding="ascii")
    verify(PUBLIC, statement(VERSION, ASSET, blake3(asset.read_bytes()).hexdigest()), signature)
    assert str(tmp_path / (ASSET + ".sig")) in capsys.readouterr().out


def test_the_key_can_be_piped_in(monkeypatch, asset):
    monkeypatch.setattr("sys.stdin", io.StringIO(SECRET + "\n"))
    assert tool.main(["sign", "-", str(asset)]) == 0
    assert (asset.parent / (ASSET + ".sig")).exists()


def test_in_a_terminal_the_key_is_pasted_unseen(monkeypatch, asset):
    class Terminal(io.StringIO):
        def isatty(self):
            return True

    asked = []
    monkeypatch.setattr("sys.stdin", Terminal())
    monkeypatch.setattr(tool.getpass, "getpass", lambda prompt: asked.append(prompt) or SECRET)
    assert tool.main(["sign", "-", str(asset)]) == 0
    assert asked and "isn't shown" in asked[0]


def test_verify_checks_against_the_keys_built_in(monkeypatch, tmp_path, asset, capsys):
    key = tmp_path / "key.txt"
    key.write_text(SECRET, encoding="utf-8")
    assert tool.main(["sign", str(key), str(asset)]) == 0
    monkeypatch.setattr(tool, "RELEASE_KEYS", (PUBLIC,))
    assert tool.main(["verify", str(asset)]) == 0
    assert "signed with one of Vitralis's release keys" in capsys.readouterr().out
    monkeypatch.setattr(tool, "RELEASE_KEYS", (public_key(OTHER_SECRET),))
    assert tool.main(["verify", str(asset)]) == 1
    assert "trusts" in capsys.readouterr().err


def test_verify_says_a_missing_signature(asset, capsys):
    assert tool.main(["verify", str(asset)]) == 1
    assert "couldn't be read" in capsys.readouterr().err


def test_a_file_of_another_version_is_refused_unsigned(tmp_path, capsys):
    other = tmp_path / "vitralis-1.3.0-windows-x86_64.exe"
    other.write_bytes(b"MZ")
    key = tmp_path / "key.txt"
    key.write_text(SECRET, encoding="utf-8")
    assert tool.main(["sign", str(key), str(other)]) == 1
    assert "isn't a file of Vitralis 1.4.0" in capsys.readouterr().err
    assert not (tmp_path / (other.name + ".sig")).exists()


def test_a_secret_that_isnt_one_signs_nothing(tmp_path, asset, capsys):
    key = tmp_path / "key.txt"
    key.write_text("not a key", encoding="utf-8")
    assert tool.main(["sign", str(key), str(asset)]) == 1
    assert "nothing was signed" in capsys.readouterr().err
    assert not (asset.parent / (ASSET + ".sig")).exists()


@pytest.mark.parametrize("arguments", [[], ["sign", "key"], ["verify"], ["keygen"], ["dance"]])
def test_wrong_arguments_print_the_usage(arguments, capsys):
    assert tool.main(arguments) == 1
    assert "usage" in capsys.readouterr().err


def test_a_missing_key_file_or_asset_is_said(tmp_path, capsys):
    assert tool.main(["public", str(tmp_path / "none.txt")]) == 1
    assert "couldn't be read" in capsys.readouterr().err
    key = tmp_path / "key.txt"
    key.write_text(SECRET, encoding="utf-8")
    assert tool.main(["sign", str(key), str(tmp_path / ASSET)]) == 1
    assert "couldn't be read" in capsys.readouterr().err


def test_sign_can_be_run_as_a_module(asset):
    import subprocess
    import sys

    result = subprocess.run([sys.executable, "-m", "vitralis.sign"], capture_output=True, text=True)
    assert result.returncode == 1 and "usage" in result.stderr


def test_no_standard_input_at_all_is_said(monkeypatch, asset, capsys):
    monkeypatch.setattr("sys.stdin", None)
    assert tool.main(["sign", "-", str(asset)]) == 1
    assert "no standard input" in capsys.readouterr().err


def test_a_checkout_whose_version_isnt_one_signs_nothing(monkeypatch, tmp_path, asset, capsys):
    monkeypatch.setattr(tool, "current_version", lambda: None)
    key = tmp_path / "key.txt"
    key.write_text(SECRET, encoding="utf-8")
    assert tool.main(["sign", str(key), str(asset)]) == 1
    assert "isn't a version" in capsys.readouterr().err


def test_a_signature_that_cant_be_written_is_said(monkeypatch, tmp_path, asset, capsys):
    key = tmp_path / "key.txt"
    key.write_text(SECRET, encoding="utf-8")
    real = type(asset).write_text

    def refuse(self, *args, **kwargs):
        if self.suffix == ".sig":
            raise PermissionError("read-only")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(type(asset), "write_text", refuse)
    assert tool.main(["sign", str(key), str(asset)]) == 1
    assert "couldn't be written" in capsys.readouterr().err

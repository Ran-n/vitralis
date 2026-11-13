#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 00:23:14.623282
Revised: 2026/11/14 00:23:23.163701

Every sentence the app can show is translated: the source is scanned for what is passed to ``t(...)`` (a
literal, or a module constant holding one) and for the tables of keys, and each must exist in every language
with the same placeholders. A new sentence without its translations fails here, whichever module adds it,
and so does a translation of a sentence the source no longer holds.
"""

import ast
import re
from pathlib import Path

import pytest

import vitralis
from vitralis.licence import messages as licence_messages
from vitralis.licence.section import _ROWS
from vitralis.settings import _ACTION_KEYS, LANGUAGES
from vitralis.styles import TOOL_ICONS
from vitralis.translations import _TRANSLATIONS, set_language, t
from vitralis.tray import MENU
from vitralis.updates import messages as update_messages

SOURCE = Path(vitralis.__file__).parent
OTHERS = [language for language in _TRANSLATIONS if language != "English"]


def _constants(tree: ast.Module) -> dict[str, str]:
    """Module-level ``NAME = "text"`` assignments (adjacent string pieces are already one constant)."""
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found[target.id] = node.value.value
    return found


def _texts(node: ast.expr, constants: dict[str, str]) -> set[str]:
    """What ``t`` is given: a literal, a module constant, or either branch of ``a if x else b``."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.Name) and node.id in constants:
        return {constants[node.id]}
    if isinstance(node, ast.IfExp):
        return _texts(node.body, constants) | _texts(node.orelse, constants)
    return set()


def _sources() -> list[ast.Module]:
    return [
        ast.parse(path.read_text(encoding="utf-8")) for path in SOURCE.rglob("*.py") if path.name != "translations.py"
    ]


def keys_passed_to_t() -> set[str]:
    keys: set[str] = set()
    for tree in _sources():
        constants = _constants(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "t" and node.args:
                keys |= _texts(node.args[0], constants)
    return keys


def every_text_in_the_source() -> set[str]:
    """Every string literal outside the translation tables: a sentence reaches ``t`` through one of them."""
    return {
        node.value
        for tree in _sources()
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def every_key() -> set[str]:
    keys = keys_passed_to_t()
    keys |= set(_ACTION_KEYS.values()) | {tip for _, tip in TOOL_ICONS.values()} | set(MENU) | set(_ROWS)
    keys |= set(update_messages.ALL) | set(licence_messages._MESSAGES.values())
    keys |= {licence_messages.EXPIRED_ON, licence_messages.SAVE_FAILED, licence_messages.PRIVACY}
    return keys


def test_the_scan_finds_the_sentences():
    keys = every_key()
    assert len(keys) >= 100
    assert {"Draw", "Pick color", "Show toolbar", "Settings", "Version {version}"} <= keys


@pytest.mark.parametrize("language", OTHERS)
def test_every_sentence_is_translated_with_the_same_placeholders(language):
    table = _TRANSLATIONS[language]
    missing = sorted(key for key in every_key() if not table.get(key))
    assert missing == [], f"{language} lacks {missing}"
    for key in every_key():
        assert set(re.findall(r"\{\w+\}", table[key])) == set(re.findall(r"\{\w+\}", key)), (language, key)


@pytest.mark.parametrize("language", OTHERS)
def test_no_language_keeps_a_sentence_nothing_uses(language):
    unused = sorted(set(_TRANSLATIONS[language]) - every_text_in_the_source())
    assert unused == [], f"{language} translates sentences the app no longer shows: {unused}"


def test_every_language_in_settings_has_a_table_and_the_other_way_round():
    assert {label for _, label in LANGUAGES} == set(_TRANSLATIONS)


def test_an_unknown_language_or_sentence_reads_as_english():
    set_language("Klingon")
    assert t("Draw") == "Draw"
    set_language("Galego")
    assert t("Draw") == "Debuxar" and t("no such sentence") == "no such sentence"

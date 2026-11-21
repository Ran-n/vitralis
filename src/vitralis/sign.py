#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/15 14:24:48.077286
Revised: 2026/11/21 18:29:10.841480

``vitralis-sign``: makes and checks the ``.minisig`` files the updater trusts (``vitralis.updates.signature``),
in minisign's format, so anyone can also check one with ``minisign -Vm <file> -P <key>``.

    vitralis-sign keygen <secret-file>          a new key in a new file; prints its public half
    vitralis-sign public <secret-file>          prints the public half again, in hex and in minisign's form
    vitralis-sign sign <secret-file> <asset>... writes <asset>.minisig next to each
    vitralis-sign verify <asset>...             checks each .minisig against the keys built into Vitralis
    vitralis-sign keys                          prints the built-in keys in minisign's form, signing key first

``<secret-file>`` may be ``-``: in a terminal the key is then pasted at a prompt that doesn't show it, and
otherwise read from standard input (``gpg --batch -q -d <key>.gpg | vitralis-sign sign - …``), so it never
rests in a file. Assets are signed as this checkout's version: a file whose name isn't one of that
version's is refused, so sign from the tag's checkout.
"""

import getpass
import sys
from pathlib import Path

from vitralis.updates.rules import NotSigned
from vitralis.updates.signature import RELEASE_KEYS, Unreadable, generate, minisign_public, public_key
from vitralis.updates.signature.hashes import FileHashes, hash_file
from vitralis.updates.signature.minisign import accept, check_file, sign, trusted_comment
from vitralis.updates.target import current_version, is_asset_of, signature_name

USAGE = """usage:
  vitralis-sign keygen <secret-file>
  vitralis-sign public <secret-file>
  vitralis-sign sign <secret-file> <asset>...
  vitralis-sign verify <asset>...
  vitralis-sign keys
<secret-file> may be - to paste the key unseen, or to pipe it in."""


class Refused(Exception):
    """A reason to stop, said on standard error."""


def read_secret(where: str) -> str:
    if where == "-":
        if sys.stdin is not None and sys.stdin.isatty():
            return getpass.getpass("Paste the release key (it isn't shown), then press Enter: ").strip()
        if sys.stdin is None:
            raise Refused("there is no standard input to read the key from")
        return sys.stdin.read().strip()
    try:
        return Path(where).read_text(encoding="utf-8").strip()
    except OSError as ex:
        raise Refused(f"{where} couldn't be read: {ex}") from ex


def keygen(where: str) -> None:
    secret = generate()
    try:
        with Path(where).open("x", encoding="utf-8") as file:  # never over an existing key
            file.write(secret + "\n")
    except OSError as ex:
        raise Refused(f"{where} couldn't be created: {ex}") from ex
    print(public_key(secret))


def _public(secret: str) -> str:
    try:
        return public_key(secret)
    except Unreadable as ex:
        raise Refused(f"{ex}; nothing was signed") from ex


def asset_hashes(asset: Path) -> tuple[str, FileHashes]:
    """The trusted comment a file of this checkout's version is signed with, and the file's hashes."""
    version = current_version()
    if version is None:
        raise Refused("this checkout's version isn't a version")
    if not is_asset_of(asset.name, version):
        raise Refused(f"{asset.name} isn't a file of Vitralis {version}, the version of this checkout")
    try:
        hashes = hash_file(asset)
    except OSError as ex:
        raise Refused(f"{asset} couldn't be read: {ex}") from ex
    return trusted_comment(version, asset.name, hashes.blake3), hashes


def sign_assets(secret: str, assets: list[Path]) -> None:
    _public(secret)  # a key that isn't one is said before anything is written
    for asset in assets:
        path = asset.with_name(signature_name(asset.name))
        comment, hashes = asset_hashes(asset)
        text = sign(secret, hashes.blake2b, comment)
        try:
            path.write_text(text, encoding="ascii", newline="\n")
        except OSError as ex:
            raise Refused(f"{path} couldn't be written: {ex}") from ex
        print(path)


def verify_assets(assets: list[Path]) -> None:
    """Against the keys built into Vitralis, never a test key from the environment."""
    keys = RELEASE_KEYS
    for asset in assets:
        path = asset.with_name(signature_name(asset.name))
        try:
            signature = path.read_text(encoding="ascii")
        except (OSError, UnicodeDecodeError) as ex:
            raise Refused(f"{path} couldn't be read: {ex}") from ex
        comment, hashes = asset_hashes(asset)
        try:
            key, minisig = accept(keys, signature, comment)
            check_file(key, minisig, hashes.blake2b)
        except (NotSigned, Unreadable) as ex:
            raise Refused(f"{asset}: {ex}") from ex
        print(f"{asset}: signed with one of Vitralis's release keys")


def run(arguments: list[str]) -> None:
    match arguments:
        case ["keygen", where]:
            keygen(where)
        case ["public", where]:
            public = _public(read_secret(where))
            print(public)
            print(minisign_public(public))
        case ["sign", where, *assets] if assets:
            sign_assets(read_secret(where), [Path(asset) for asset in assets])
        case ["verify", *assets] if assets:
            verify_assets([Path(asset) for asset in assets])
        case ["keys"]:
            for key in RELEASE_KEYS:
                print(minisign_public(key))
        case _:
            raise Refused(USAGE)


def main(argv: list[str] | None = None) -> int:
    try:
        run(sys.argv[1:] if argv is None else argv)
    except Refused as ex:
        print(ex, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

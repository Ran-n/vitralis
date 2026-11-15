#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/15 14:24:48.077286
Revised: 2026/11/15 14:24:48.077286

``vitralis-sign``: makes and checks the ``.sig`` files the updater trusts (``vitralis.updates.signature``).

    vitralis-sign keygen <secret-file>          a new key in a new file; prints its public half
    vitralis-sign public <secret-file>          prints the public half again
    vitralis-sign sign <secret-file> <asset>... writes <asset>.sig next to each
    vitralis-sign verify <asset>...             checks each .sig against the keys built into Vitralis

``<secret-file>`` may be ``-``: in a terminal the key is then pasted at a prompt that doesn't show it, and
otherwise read from standard input (``keepassxc-cli show -s -a Password … | vitralis-sign sign - …``), so it
never rests in a file. Assets are signed as this checkout's version: a file whose name isn't one of that
version's is refused, so sign from the tag's checkout.
"""

import getpass
import sys
from pathlib import Path

from blake3 import blake3

from vitralis.updates.rules import NotSigned
from vitralis.updates.signature import RELEASE_KEYS, Unreadable, generate, public_key, sign, statement, verify_any
from vitralis.updates.target import current_version, is_asset_of, signature_name

USAGE = """usage:
  vitralis-sign keygen <secret-file>
  vitralis-sign public <secret-file>
  vitralis-sign sign <secret-file> <asset>...
  vitralis-sign verify <asset>...
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


def asset_statement(asset: Path) -> bytes:
    version = current_version()
    if version is None:
        raise Refused("this checkout's version isn't a version")
    if not is_asset_of(asset.name, version):
        raise Refused(f"{asset.name} isn't a file of Vitralis {version}, the version of this checkout")
    hasher = blake3()
    try:
        with asset.open("rb") as file:
            for chunk in iter(lambda: file.read(1 << 20), b""):
                hasher.update(chunk)
    except OSError as ex:
        raise Refused(f"{asset} couldn't be read: {ex}") from ex
    return statement(version, asset.name, hasher.hexdigest())


def sign_assets(secret: str, assets: list[Path]) -> None:
    _public(secret)  # a key that isn't one is said before anything is written
    for asset in assets:
        path = asset.with_name(signature_name(asset.name))
        text = sign(secret, asset_statement(asset))
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
        try:
            verify_any(keys, asset_statement(asset), signature)
        except (NotSigned, Unreadable) as ex:
            raise Refused(f"{asset}: {ex}") from ex
        print(f"{asset}: signed with one of Vitralis's release keys")


def run(arguments: list[str]) -> None:
    match arguments:
        case ["keygen", where]:
            keygen(where)
        case ["public", where]:
            print(_public(read_secret(where)))
        case ["sign", where, *assets] if assets:
            sign_assets(read_secret(where), [Path(asset) for asset in assets])
        case ["verify", *assets] if assets:
            verify_assets([Path(asset) for asset in assets])
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

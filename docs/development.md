[//]: # ( ---------------------------------------------------------------------- )
[//]: # (+ Authors: 	Ran# <ran.hash@proton.me> )
[//]: # (+ Created: 	2026/11/15 16:41:04.658676 )
[//]: # (+ Revised: 	2026/11/15 21:40:06.852046 )
[//]: # ( ---------------------------------------------------------------------- )

# Developing Vitralis

How to run Vitralis from source, test it, build it and release it. [CONTRIBUTING.md](../CONTRIBUTING.md) says
how to propose a change; [design-decisions.md](design-decisions.md) says why some things are the way they are.

## Contents

- [Run from source](#run-from-source)
- [Layout](#layout)
- [Tests](#tests)
- [Build](#build)
- [Checking the updater and the installer](#checking-the-updater-and-the-installer)
- [Releases](#releases)

## Run from source

Python 3.13 and [uv](https://docs.astral.sh/uv/), on Windows:

```
uv sync
uv run vitralis
```

Logs go to `%APPDATA%\Vitralis\vitralis.log`, errors nothing else caught included. Only one Vitralis runs per
Windows account. Run from source, Vitralis is a build from source: it never checks for updates.

## Layout

| Folder | What it holds |
|---|---|
| `src/vitralis` | the app: overlay (`canvas`, `renderer`), toolbar and its windows, settings, persistence |
| `src/vitralis/licence` | the license gate and its Clavren client |
| `src/vitralis/updates` | the updater: rules, release target and file names, signatures, forges, download, install, its Settings section |
| `src/vitralis/sign.py` | `vitralis-sign`, the release signing tool |
| `packaging/windows` | the Inno Setup installer, `build-installer.ps1` and `test-installer.ps1` |
| `tests` | the tests; `tests/rendered` drives the real windows, `tests/updates/golden` holds the forges' answers |
| `docs` | the landing page (served by GitHub, GitLab and Codeberg Pages) and these guides |

## Tests

```
uv run pytest
```

With the coverage gate (branch coverage of `src/vitralis`, as CI runs it), and the linter:

```
uv run pytest --cov
uv run ruff format --check . && uv run ruff check .
```

The tests never touch your own `%APPDATA%\Vitralis`: each one gets a data folder of its own.

The contract tests against the real license server are left out of the default run. `uv run pytest -m live` checks that the server refuses an unknown key; with a Vitralis test license's key in an environment variable it also activates and checks that license (never write a key in the repository; each run with a key adds an activation named `<computer> (live test)`):

```
VITRALIS_LICENCE_TEST_KEY=BRN-... uv run pytest -m live
```

The rendered tests (`tests/rendered`, Windows only) are left out of the default run too, because they need a real Windows desktop and take about a minute: the real toolbar, its windows and a small overlay run in a process of their own, with a license and an update feed held in memory. Their windows are cloaked, so nothing shows on your screen, in the taskbar or in Alt+Tab, and they never take the focus; `VITRALIS_SHOW_TEST_WINDOW=1` shows them, to watch a run. Their scratch data folder is under `%PUBLIC%
itralis-tests` (deleted afterwards), not your Temp folder, because a path under your profile would put your user name in the pictures, and every state the test copy reports, with every text on its windows, is searched for your user name: a hit fails the test before a picture is taken. Look at every picture before approving it all the same. They click and drag by posting window messages and look at the windows with `PrintWindow`, so your mouse, keyboard, running Vitralis and its data are left alone. Each test checks the pixels a click leaves and what it saved, and the windows are compared with the reviewed pictures in `tests/rendered/baselines` (the test copy draws one pixel per pixel whatever the monitors' scaling, so the pictures don't follow your screens):

```
uv run pytest -m desktop --no-cov
VITRALIS_SHOW_TEST_WINDOW=1 uv run pytest -m desktop --no-cov   # with the windows on the screen
```

After a deliberate change of look, write the pictures again, look at each one, and commit them with the change (what differs on a failure is written to `tests/rendered/failures`):

```
VITRALIS_UPDATE_BASELINES=1 uv run pytest -m desktop --no-cov
```

## Build

```
uv run build
```

It builds the one-file exe `dist/vitralis-<version>-windows-x86_64.exe` (PyInstaller) and then the installer `dist/vitralis-<version>-windows-x86_64-setup.exe` with [packaging/windows/build-installer.ps1](../packaging/windows/build-installer.ps1), which needs [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`; it looks on PATH and in Inno Setup's usual folders, or takes `-Compiler` or `ISCC`). `uv run build --no-installer` builds only the exe. Without `VITRALIS_RELEASE_TARGET=windows-x86_64` the exe is a build from source, which never updates itself; releases are built by the [release workflow](../.github/workflows/release.yml) with it set (see [Releases](#releases)).

Test an installer for real, in a scratch folder it cleans up after itself (it refuses to run over an installed Vitralis; see the script for how to test beside one):

```
powershell -File packaging/windows/test-installer.ps1 -Installer dist/vitralis-<version>-windows-x86_64-setup.exe
```

## Checking the updater and the installer

The in-app updater's whole path runs in the tests against a release server
on localhost (`tests/updates`): the check against both forges' golden
answers, the proof (checksum and signature) before any byte of the exe, the
download and its limits, and a real running exe swapped on Windows. A copy
run from source can be pointed at your own server and key for a manual try;
the packaged exe ignores all of these:

- `VITRALIS_RELEASE_TARGET=windows-x86_64`: act as a release build
- `VITRALIS_UPDATE_SOURCES=<github-url>|<gitlab-url>`: ask these instead
  (plain HTTP allowed)
- `VITRALIS_UPDATE_KEY=<public key>`: trust this key instead of the release
  keys
- `VITRALIS_UPDATE_DIR=<folder>`: download here

`packaging/windows/test-installer.ps1` installs a built installer for real
into a scratch folder under `build/`, checks the exe, the Settings → Apps
entry, both shortcuts and `vitralis.exe --version`, installs again over
itself, uninstalls and fails if anything is left (the release workflow runs
it too). With Vitralis installed, build and test one with an identity of
its own: pass `-AppId <new GUID> -AppName "Vitralis Installer Test"
-AppKey "Software\Vitralis Installer Test"` to both scripts, plus
`-AppMutex VitralisInstallerTest` to `build-installer.ps1` and
`-OutputDirectory` to keep it apart from `dist/`. Never release an
installer built that way. A new app language needs an installer one too: a
`[Languages]` line and its `StartWithWindows` and `AppLanguage` messages in
`packaging/windows/vitralis.iss` (the tests check they match).

Never change `INSTALLER_GUID` in `src/vitralis/installed.py`:
Windows tells installs apart by it.

## Releases

A release has four files, each with a BLAKE3 `.b3` and a `.sig`, its
signature by the release key: twelve files in all. The updater installs
nothing without a valid `.sig` (see [design-decisions.md](design-decisions.md)).

| Built on | File |
|----------|------|
| `windows-latest` | `vitralis-<version>-windows-x86_64.exe` (portable; what the updater downloads) |
| `windows-latest` | `vitralis-<version>-windows-x86_64-setup.exe` (installer) |
| `windows-latest` | `vitralis-<version>-py3-none-any.whl` |
| `windows-latest` | `vitralis-<version>.tar.gz` |

The exe's name comes from `vitralis.updates.target.asset_name`; the
workflow asks `uv run vitralis-asset-name windows-x86_64` instead of
spelling it out.

Vitralis trusts two release keys, `RELEASE_KEYS` in
`src/vitralis/updates/signature.py`: the first signs every release, the
second is a backup. A secret key is one line of hex and lives in a password
manager, never in the repository, a plain file, CI or a forge: the signing
key in the KeePass database used for releases, the backup somewhere
separate, so one loss or theft never takes both.

`uv run vitralis-sign` has four commands: `keygen <secret-file>` makes a
key and prints its public half (it never overwrites a file), `public
<secret-file>` prints it again, `sign <secret-file> <asset>...` writes each
`<asset>.sig`, and `verify <asset>...` checks each against `RELEASE_KEYS`.
`<secret-file>` may be `-`: in a terminal you paste the key (it isn't
shown); otherwise it is read from standard input, for KeePassXC's command
line:

```sh
keepassxc-cli show -s -a Password <database.kdbx> "Vitralis release key" \
  | uv run vitralis-sign sign - <asset>...
```

Assets are signed as the checkout's version, so sign from the tag.

`keygen` writes a file, so it is only for test keys. A release key is made
inside KeePassXC, so it never exists outside it, and its public half is
read back through `public -`:

```sh
keepassxc-cli add -g -L 64 -c 0123456789abcdef <database.kdbx> "Vitralis release key"
keepassxc-cli show -s -a Password <database.kdbx> "Vitralis release key" \
  | uv run vitralis-sign public -
```

The backup key is made the same way, in a separate database.

1. Promote **Unreleased** in the changelog to `## [X.Y.Z]` and set the
   version (`uv version X.Y.Z`); run `uv run pytest --cov`, `-m live` (with
   the test key) and `-m desktop`.
2. Push the tag `vX.Y.Z`. [release.yml](../.github/workflows/release.yml) fails
   at once if the tag and `pyproject.toml` disagree, then builds the exe and
   the installer as release builds, tests the installer, adds the wheel and
   the sdist, checksums and attests all four, and creates a **draft** GitHub
   release with the eight files and that version's changelog section.
3. Download the draft's files, check each with `b3sum --check <file>.b3`,
   and check each is what the workflow built from this tag:
   `gh attestation verify <file> --repo Ran-n/vitralis`. Sign nothing that
   fails either check.
4. From the tag's checkout, sign the four files (not the `.b3` files) with
   the key pasted or piped from KeePassXC, check them with
   `uv run vitralis-sign verify <file>...`, and add the four `.sig` files to
   the draft (`gh release upload vX.Y.Z *.sig`).
5. Attach the same twelve files to the GitLab release
   (`glab release create vX.Y.Z <files>`) and the Codeberg one. GitLab must
   have every file, `.b3` and `.sig`: the updater asks it on every check,
   beside GitHub.
6. Publish the GitHub draft. The updater only sees published releases that
   aren't pre-releases.

If the signing key is lost or stolen: sign the next release with the backup
key, and in that release replace `RELEASE_KEYS` with the backup and a newly
generated key. Everyone who installs it stops trusting the old key; until
they do, a stolen key can still sign for them, so ship that release at once.
Losing both keys means everyone downloads the next version by hand, so never
regenerate either casually.

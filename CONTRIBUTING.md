[//]: # ( ---------------------------------------------------------------------- )
[//]: # (+ Authors: 	Ran# <ran.hash@proton.me> )
[//]: # (+ Created: 	2026/08/04 12:07:07.959602 )
[//]: # (+ Revised: 	2026/11/13 20:12:35.250163 )
[//]: # ( ---------------------------------------------------------------------- )

Thank you for your interest in contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Features](#suggesting-features)
- [Submitting Changes](#submitting-changes)
- [Backlog](#backlog)
- [Commit Style](#commit-style)
- [License](#license)

---

## Code of Conduct

Be respectful. No harassment, discrimination, or bad-faith participation
will be tolerated.

---

## Reporting Bugs

Open an issue with:

- A clear, descriptive title
- Steps to reproduce
- Expected vs. actual behavior
- Your environment (OS, versions, etc.)

---

## Suggesting Features

Open an issue with:

- The problem you're trying to solve
- Your proposed solution
- Any alternatives you considered

---

## Submitting Changes

1. Fork the repository
2. Branch from `main`
3. Make your change, with tests; `uv run pytest` must pass (the live
   license test runs only with `-m live` and `VITRALIS_LICENCE_TEST_KEY`;
   never commit a license key)
4. Commit following the [Commit Style](#commit-style) below
5. Open a pull request against `main`
6. Describe why the change is needed, not just what it does

Keep one concern per pull request.

To check the in-app updater end to end, on Windows:

1. Build two versions, N and N+1: set the version (`uv version 1.3.98`), run
   `uv run build`, then again with `uv version 1.3.99`; put the version back
   afterwards
2. Write `vitralis-<N+1>.exe.b3` next to the N+1 exe (`b3sum`, or Python's
   `blake3`) and serve both, plus a release JSON like GitHub's
   (`tag_name`, `html_url`, `assets[].name` and `browser_download_url`), on
   `http://127.0.0.1:<port>/`
3. Copy the N exe into a folder of your own and start it with
   `VITRALIS_RELEASES_URL=http://127.0.0.1:<port>/<json path>`
4. Settings → Updates → **Install**, then **Restart to update**
5. Confirm that N+1 starts licensed at the same path, says "Updated to …",
   that `<exe>.old` and `%APPDATA%\Vitralis\updates` are gone, and that only
   one Vitralis is running; serving an exe with one changed byte must give
   the checksum error and swap nothing

To check the installer, on Windows, after `uv run build`:

1. `dist\vitralis-<version>-setup.exe /VERYSILENT /DIR=<scratch folder>
   /TASKS=desktopicon`
2. Confirm `Vitralis.exe` is in the folder, the Start menu and desktop
   shortcuts exist, and Settings → Apps lists Vitralis with the version
3. Run the same installer again with `/VERYSILENT`: it must reuse the folder
4. `<scratch folder>\unins000.exe /VERYSILENT`: the folder, both shortcuts,
   the Settings → Apps entry and `HKCU\Software\Vitralis` are gone,
   `%APPDATA%\Vitralis` is kept
5. With `/LANG=glr` (or `gl`, `zh`, `ja`, …), `HKCU\Software\Vitralis`
   holds that language as Settings names it, and a fresh Vitralis starts in
   it. A new app language needs an installer one too: a `[Languages]` line
   and its `StartWithWindows` and `AppLanguage` messages in
   `installer/vitralis.iss` (the tests check they match)

Never change `INSTALLER_GUID` in `src/vitralis/installed.py`:
Windows tells installs apart by it.

---

## Backlog

Planned work lives in [TODO.md](TODO.md): one self-contained item per
change, top to bottom in priority order.

---

## Commit Style

Titles use a bracketed tag followed by a short imperative summary; bodies
follow [Conventional Commits](https://www.conventionalcommits.org/).

| Bracket | Meaning |
|---------|---------|
| `[A]`   | Add — new feature or file |
| `[R]`   | Remove |
| `[F]`   | Fix |
| `[U]`   | Update — change to existing behavior |
| `[D]`   | Docs |
| `[C]`   | Chore |

Rules:

- Title is lowercase and imperative (`add x`, not `added x` or `Added X`)
- Body explains why, not just what
- No `Co-Authored-By` trailers

---

## License

This project is licensed under the PayBack License (PBL) v2.0:

- Free for personal and non-commercial use
- Commercial use requires a revenue share
- Contributing does not transfer copyright
- Non-trivial contributions may entitle a revenue share, pending a
  CONTRIBUTORS listing and quorum vote

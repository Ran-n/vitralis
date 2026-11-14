[//]: # ( ---------------------------------------------------------------------- )
[//]: # (+ Authors: 	Ran# <ran.hash@proton.me> )
[//]: # (+ Created: 	2026/04/27 10:48:03.565778 )
[//]: # (+ Revised: 	2026/11/14 16:56:41.171448 )
[//]: # ( ---------------------------------------------------------------------- )

![Vitralis icon](src/vitralis/media/logo/icon_title.png)

# Vitralis

> *Vitralis* — from Latin *vitreus*, of glass. A surface that is there without being in the way.

Your screen, with memory.

Draw annotations, shapes, and marks directly over your live desktop. They stay — across sessions, across reboots — until you decide to remove them. The rest of the time, the overlay is invisible to your mouse: click through it as if it weren't there.

## Features

- Transparent, always-on-top overlay spanning all monitors
- Always click-through — use your computer normally at all times
- Drawing activated via a small floating toolbar; it stays on for as many strokes as you need, until a right-click or Esc
- Tools: freehand pen, eraser, rectangle, ellipse, line, arrow
- Color palette with a custom color picker (pick a shade or type `#rrggbb`), stroke size control, and scroll-wheel color cycling
- Per-stroke undo (the latest stroke, whichever monitor it is on) and click-to-delete individual strokes
- Pan mode — drag all drawings to reposition them
- Drawings persist across restarts (JSON stroke list, per-monitor), and so do the toolbar's tool, color, size and position
- Named snapshots: save the drawings of every monitor and load them back later
- Follows your monitors: plug one in, unplug it or change its resolution and the overlay adapts
- Show/hide overlay without losing drawings
- System tray icon — lives quietly in the background; starting Vitralis again just brings its toolbar back
- Info panel — version, author, and license at a glance
- License key — activated once per computer, works offline for up to 30 days
- Tells you when a new version is out (Settings → Updates), and installs it from inside the app

## Install

From the [latest release](https://github.com/Ran-n/vitralis/releases/latest), on Windows (64-bit):

- **`vitralis-<version>-setup.exe`**, the installer. It installs for your account only, with no admin prompt, in `%LOCALAPPDATA%\Programs\Vitralis`, adds Vitralis to the Start menu, and can add a desktop shortcut and start Vitralis when you sign in. Uninstall it from Windows's Settings → Apps. Your settings, drawings and license (`%APPDATA%\Vitralis`) stay, so installing again needs no new key. Running a newer version's installer updates it in place. It speaks every language Vitralis does, and Vitralis starts in the one you install in until you pick another in Settings.
- **`vitralis-<version>.exe`**, the portable version: one file, nothing installed. Put it in a folder of your own and run it.

Both update themselves from inside the app (see [Updates](#updates)). Every file has a `.b3` BLAKE3 checksum next to it (`b3sum -c vitralis-<version>-setup.exe.b3`).

## License key

Vitralis needs a license key (`BRN-XXXX-XXXX-XXXX-XXXX`). On first start it shows a license window instead of the overlay: type the key and press **Activate**. No key yet? Ask ran.hash@proton.me for one.

- **One key, one computer.** A key works on the first computer it's activated on. After a reinstall or a new PC, ask for a reset and enter the same key again.
- **Works offline.** Vitralis checks the license once a day when online, and keeps working on its saved license for up to 30 days without internet.
- **Settings → License** shows whether it's a test license, until when it's valid, and until when it works offline (highlighted when under 5 days away), with **Check now**.
- If the license is revoked, expires, or needs an online check, Vitralis closes the overlay and shows the license window again with the reason.

**What is sent, and where.** Keys are checked by Clavren at `clavren.breren.com`. Activating sends the key; after that, once a day, Vitralis sends a check signed by this computer, with the computer's name and the app version. The saved license (`%APPDATA%\Vitralis\licence.dat`) is encrypted for your Windows account and useless when copied to another account or computer.

## Updates

At start (after 10 seconds) and then once a day, Vitralis asks GitHub for the latest release. When a newer one is out, the toolbar's Settings button gets an orange dot, the tray says **Vitralis {version} is out** once, and **Settings → Updates** shows it with **Release notes** and **Skip this version** (a skipped version stays quiet until a newer one comes out; **Don't skip** undoes it). The **Check for new versions** switch turns the automatic checks off; **Check now** still works. If a check fails (offline, GitHub's hourly limit), Settings → Updates says why.

**Updating.** In the Windows exe, Settings → Updates (or a click on the tray message) offers **Install {version}**. It downloads the new exe to `%APPDATA%\Vitralis\updates`, showing the progress, and checks it against the release's BLAKE3 checksum; a damaged download is deleted and you can try again. **Restart to update** then quits Vitralis cleanly, puts the new exe at the same path as the old one (so shortcuts and pinned icons keep working, even though the file name keeps the old version), and starts it; it says **Updated to {version}** once and needs no new license key. If anything goes wrong, the old exe is put back and keeps running. The exe's folder must be writable, as the installer's is: under `C:\Program Files`, move Vitralis to a folder of your own or update by hand. In an installed Vitralis, Settings → Apps shows the new version after the restart. Running from source, only Release notes is offered.

## Setup

```
uv sync
```

## Usage

```
uv run vitralis
```

Or directly:

```
uv run python -m vitralis
```

Logs go to `%APPDATA%\Vitralis\vitralis.log`, errors nothing else caught included. Only one Vitralis runs per Windows account.

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

The contract test against the real license server is left out of the default run. Run it with a Vitralis test license's key in an environment variable (never write a key in the repository; each run adds an activation named `<computer> (live test)`):

```
VITRALIS_LICENCE_TEST_KEY=BRN-... uv run pytest -m live
```

The rendered tests (`tests/rendered`, Windows only) are left out of the default run too, because they put real windows on your screen for about a minute: the real toolbar, its windows and a small overlay run in a process of their own on a scratch data folder, with a license and an update feed held in memory. They click and drag by posting window messages and look at the windows with `PrintWindow`, so your mouse, keyboard, running Vitralis and its data are left alone. Each test checks the pixels a click leaves and what it saved, and the windows are compared with the reviewed pictures in `tests/rendered/baselines` (taken at 100 % scaling; at another scaling those comparisons are skipped):

```
uv run pytest -m desktop --no-cov
```

After a deliberate change of look, write the pictures again, look at each one, and commit them with the change (what differs on a failure is written to `tests/rendered/failures`):

```
VITRALIS_UPDATE_BASELINES=1 uv run pytest -m desktop --no-cov
```

## Build

```
uv run build
```

It builds the one-file exe `dist/vitralis-<version>.exe` (PyInstaller) and, from [installer/vitralis.iss](installer/vitralis.iss), the installer `dist/vitralis-<version>-setup.exe`. The installer needs [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`): `build` looks for `ISCC.exe` on PATH and in Inno Setup's usual folders, or takes its path from `ISCC`. `uv run build --no-installer` builds only the exe.

## Keyboard shortcuts

### Global (work from any app)

| Key | Action |
|---|---|
| `F8` | Focus/unfocus Vitralis toolbar — restores previous window on unfocus |

### Local (when Vitralis is focused)

| Key | Action | Key | Action |
|---|---|---|---|
| `D` | Toggle draw mode | `P` | Pen |
| `G` | Toggle pan mode | `E` | Eraser |
| `X` | Toggle delete mode | `L` | Line |
| `Z` | Undo last stroke | `A` | Arrow |
| `Del` | Clear all | `R` | Rectangle |
| `H` | Hide/show overlay | `O` | Ellipse |
| `[` / `]` | Decrease / increase size | `Right-click` | Exit active mode |
| `Scroll wheel` | Cycle through palette colors | | |
| `Esc` | Close the open panel, else leave the active mode, else quit | `Ctrl+Q` | Quit |

## License

[PayBack License (PBL) v2.0](LICENSE) — free for personal, academic, and non-commercial use. Commercial use requires a revenue-share agreement with the author. See [LICENSE](LICENSE) for full terms.

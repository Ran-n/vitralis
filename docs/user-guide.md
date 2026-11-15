[//]: # ( ---------------------------------------------------------------------- )
[//]: # (+ Authors: 	Ran# <ran.hash@proton.me> )
[//]: # (+ Created: 	2026/11/15 16:41:04.380156 )
[//]: # (+ Revised: 	2026/11/15 16:41:04.380156 )
[//]: # ( ---------------------------------------------------------------------- )

# Vitralis user guide

Everything Vitralis does and how to use it. The [README](../README.md) is the short tour.

## Contents

- [Installing](#installing)
- [Drawing](#drawing)
- [Keyboard shortcuts](#keyboard-shortcuts)
- [The license key](#the-license-key)
- [Updates](#updates)
- [Where your data lives](#where-your-data-lives)

## Installing

From the [latest release](https://github.com/Ran-n/vitralis/releases/latest), on Windows 10 (1809) or later, 64-bit:

- **`vitralis-<version>-windows-x86_64-setup.exe`**, the installer. It installs for your account only, with no admin prompt, in `%LOCALAPPDATA%\Programs\Vitralis`, adds Vitralis to the Start menu, and can add a desktop shortcut and start Vitralis when you sign in. Uninstall it from Windows's Settings → Apps. Your settings, drawings and license (`%APPDATA%\Vitralis`) stay, so installing again needs no new key. Running a newer version's installer updates it in place. It speaks every language Vitralis does, and Vitralis starts in the one you install in until you pick another in Settings.
- **`vitralis-<version>-windows-x86_64.exe`**, the portable version: one file, nothing installed. Put it in a folder of your own and run it.

Both update themselves from inside the app (see [Updates](#updates)). Every file has a `.b3` BLAKE3 checksum next to it (`b3sum -c vitralis-<version>-windows-x86_64-setup.exe.b3`) and a `.sig`, its signature by Vitralis's release key, which the in-app updater checks. The wheel and the source archive are attached too, for running from Python. `vitralis.exe --version` prints the version.

## Drawing

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

## The license key

Vitralis needs a license key (`BRN-XXXX-XXXX-XXXX-XXXX`). On first start it shows a license window instead of the overlay: type the key and press **Activate**. No key yet? Ask ran.hash@proton.me for one.

- **One key, one computer.** A key works on the first computer it's activated on. After a reinstall or a new PC, ask for a reset and enter the same key again.
- **Works offline.** Vitralis checks the license once a day when online, and keeps working on its saved license for up to 30 days without internet.
- **Settings → License** shows whether it's a test license, until when it's valid, and until when it works offline (highlighted when under 5 days away), with **Check now**.
- If the license is revoked, expires, or needs an online check, Vitralis closes the overlay and shows the license window again with the reason.

**What is sent, and where.** Keys are checked by Clavren at `clavren.breren.com`. Activating sends the key; after that, once a day, Vitralis sends a check signed by this computer, with the computer's name and the app version. The saved license (`%APPDATA%\Vitralis\licence.dat`) is encrypted for your Windows account and useless when copied to another account or computer.

## Updates

A minute after start, and then a day after the last check that worked (an hour after one that didn't), Vitralis asks GitHub and GitLab, both at once, for the latest release. When a newer one is out, the toolbar's Settings button gets an orange dot, the tray says **Vitralis {version} is available.** once (a click opens Settings), and **Settings → Updates** shows it with **Release notes** and **Skip this version** (a skipped version stays quiet until a newer one comes out; **Stop skipping {version}** undoes it and checks again). **Check for updates automatically** turns the automatic checks off; **Check now** still works. If a check fails, Settings → Updates says why for each forge ("GitHub: the server answered 429; GitLab: the request timed out"), and keeps showing a version it already knew of. A pre-release is only offered to a pre-release.

**Updating.** In the release exe, **Update and restart** first reads the release's checksum and signature and checks that the signature is by Vitralis's release key and names this version, this file and that checksum. Only then does it download the new exe into `%LOCALAPPDATA%\Vitralis\updates`, showing the progress (**Cancel** stops it), and compare it with the checksum. Then it quits Vitralis cleanly, puts the new exe at the same path as the old one (so shortcuts and pinned icons keep working), and starts it; it says **Updated to {version}** once and needs no new license key. A download that isn't signed, doesn't match its checksum, or can't be put in place is deleted and said in plain words, with the release page to download it by hand; the old exe keeps running. The exe's folder must be writable, as the installer's is. In an installed Vitralis, Settings → Apps shows the new version after the restart.

**What is sent.** The check is one request to each forge's public release list, with only `Accept` and `User-Agent: Vitralis/<version>`: no identifier, nothing about you or your computer. Turn **Check for updates automatically** off and Vitralis asks only when you press **Check now**.

**Built from source** (`uv run vitralis`, or an exe built without a release target), Vitralis never checks or updates itself, and Settings → Updates says to update with `git pull` and a new build.

## Where your data lives

- `%APPDATA%\Vitralis`: your drawings (`strokes.json`), settings (`settings.json`), snapshots (`snapshots\`),
  the saved license (`licence.dat`) and the log (`vitralis.log`). Uninstalling keeps it.
- `%LOCALAPPDATA%\Vitralis\updates`: an update while it downloads; it is deleted afterwards.
- `%LOCALAPPDATA%\Programs\Vitralis`: the installed program.

A file Vitralis can't read is kept aside as `<name>.damaged` (numbered when there are several) and Vitralis
starts with the defaults, so nothing you had is ever overwritten.

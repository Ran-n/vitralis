[//]: # ( ---------------------------------------------------------------------- )
[//]: # (+ Authors: 	Ran# <ran.hash@proton.me> )
[//]: # (+ Created: 	2026/04/27 10:48:03.565778 )
[//]: # (+ Revised: 	2026/11/11 11:06:52.854330 )
[//]: # ( ---------------------------------------------------------------------- )

![Vitralis icon](src/vitralis/media/logo/icon_title.png)

# Vitralis

> *Vitralis* — from Latin *vitreus*, of glass. A surface that is there without being in the way.

Your screen, with memory.

Draw annotations, shapes, and marks directly over your live desktop. They stay — across sessions, across reboots — until you decide to remove them. The rest of the time, the overlay is invisible to your mouse: click through it as if it weren't there.

## Features

- Transparent, always-on-top overlay spanning all monitors
- Always click-through — use your computer normally at all times
- Drawing activated via a small floating toolbar; finishes automatically after each stroke
- Tools: freehand pen, eraser, rectangle, ellipse, line, arrow
- Color palette with custom color picker, stroke size control, and scroll-wheel color cycling
- Per-stroke undo and click-to-delete individual strokes
- Pan mode — drag all drawings to reposition them
- Drawings persist across restarts (JSON stroke list, per-monitor)
- Show/hide overlay without losing drawings
- System tray icon — lives quietly in the background
- Info panel — version, author, and license at a glance
- License key — activated once per computer, works offline for up to 30 days

## License key

Vitralis needs a license key (`BRN-XXXX-XXXX-XXXX-XXXX`). On first start it shows a license window instead of the overlay: type the key and press **Activate**. No key yet? Ask ran.hash@proton.me for one.

- **One key, one computer.** A key works on the first computer it's activated on. After a reinstall or a new PC, ask for a reset and enter the same key again.
- **Works offline.** Vitralis checks the license once a day when online, and keeps working on its saved license for up to 30 days without internet.
- **Settings → License** shows whether it's a test license, until when it's valid, and until when it works offline (highlighted when under 5 days away), with **Check now**.
- If the license is revoked, expires, or needs an online check, Vitralis closes the overlay and shows the license window again with the reason.

**What is sent, and where.** Keys are checked by Clavren at `clavren.breren.com`. Activating sends the key; after that, once a day, Vitralis sends a check signed by this computer, with the computer's name and the app version. The saved license (`%APPDATA%\Vitralis\licence.dat`) is encrypted for your Windows account and useless when copied to another account or computer.

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

Logs go to `%APPDATA%\Vitralis\vitralis.log`.

## Tests

```
uv run pytest
```

The contract test against the real license server is left out of the default run. Run it with a Vitralis test license's key in an environment variable (never write a key in the repository; each run adds an activation named `<computer> (live test)`):

```
VITRALIS_LICENCE_TEST_KEY=BRN-... uv run pytest -m live
```

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
| `Esc` | Quit if idle | `Ctrl+Q` | Quit |

## License

[PayBack License (PBL)](LICENSE) — free for personal, academic, and non-commercial use. Commercial use requires a revenue-share agreement with the author. See [LICENSE](LICENSE) for full terms.

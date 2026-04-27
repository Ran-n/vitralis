[//]: # ( ---------------------------------------------------------------------- )
[//]: # (+ Authors: 	Ran# <ran.hash@proton.me> )
[//]: # (+ Created: 	2026/04/27 10:48:03.565778 )
[//]: # (+ Revised: 	2026/04/27 14:00:37.103422 )
[//]: # ( ---------------------------------------------------------------------- )

# ![Vitralis icon](media/icon_title.png) Vitralis

> *Vitralis* — from Latin *vitreus*, of glass. A surface that is there without being in the way.

Your screen, with memory.

Draw annotations, shapes, and marks directly over your live desktop. They stay — across sessions, across reboots — until you decide to remove them. The rest of the time, the overlay is invisible to your mouse: click through it as if it weren't there.

## Features

- Transparent, always-on-top overlay spanning all monitors
- Always click-through — use your computer normally at all times
- Drawing activated via a small floating toolbar; finishes automatically after each stroke
- Tools: freehand pen, eraser, rectangle, ellipse, line, arrow
- Color palette with custom color picker and stroke size control
- Per-stroke undo and click-to-delete individual strokes
- Pan mode — drag all drawings to reposition them
- Drawings persist across restarts (JSON stroke list, per-monitor)
- Show/hide overlay without losing drawings
- System tray icon — lives quietly in the background

## Setup

```
uv sync
```

## Usage

```
uv run python vitralis.py
```

## Keyboard shortcuts

| Key | Action |
|---|---|
| `D` | Toggle draw mode on/off |
| `Right-click` | Exit draw/pan/delete mode |
| `P` | Pen |
| `E` | Eraser |
| `L` | Line |
| `A` | Arrow |
| `R` | Rectangle |
| `O` | Ellipse |
| `Ctrl+Z` | Undo last stroke |
| `Ctrl+Shift+Del` | Clear all |
| `Ctrl+H` | Hide/show overlay |
| `Esc` | Quit |

> Shortcuts require the toolbar to be focused. Click the toolbar once if they don't respond.

## TODO

- Save and load named overlay snapshots (export/import stroke sets by name)

## License

[PayBack License (PBL)](LICENSE) — free for personal, academic, and non-commercial use. Commercial use requires a revenue-share agreement with the author. See [LICENSE](LICENSE) for full terms.

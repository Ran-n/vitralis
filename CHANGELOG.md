[//]: # ( ---------------------------------------------------------------------- )
[//]: # (+ Authors: 	Ran# <ran.hash@proton.me> )
[//]: # (+ Created: 	2026/08/04 12:03:36.212196 )
[//]: # (+ Revised: 	2026/11/14 12:01:46.936852 )
[//]: # ( ---------------------------------------------------------------------- )

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- A notice when a newer Vitralis is out: a dot on the toolbar's Settings
  button, one tray message, and Settings → Updates with **Release notes**
  and **Skip this version**, checked at start and once a day (the
  **Check for new versions** switch turns the automatic checks off).
- Installing a new version from inside Vitralis: **Install** downloads it
  and checks its BLAKE3 checksum, **Restart to update** replaces the exe at
  the same path and starts the new version, going back to the old one if
  anything fails.
- A Windows installer, `vitralis-<version>-setup.exe`, built by
  `uv run build` with Inno Setup: installs for the current user without an
  admin prompt, adds a Start menu entry and, optionally, a desktop shortcut
  and starting at sign-in, and uninstalls from Settings → Apps keeping the
  settings, drawings and license. The portable exe is still released.
  It speaks every language Vitralis does (Galego reintegrado and Chinese
  included) and asks which at the start; Vitralis then starts in that
  language until another is picked in Settings.
- After an in-app update, an installed Vitralis shows its new version in
  Settings → Apps.
- The landing page's download button gets the installer.
- The toolbar remembers its tool, color, stroke size and position between
  runs, and whether the drawings were hidden (the Show/Hide button shows
  it).
- The overlay follows the monitors: plugging one in, unplugging it or
  changing its resolution rebuilds the overlay, each monitor getting its
  own drawings back.
- Only one Vitralis runs per Windows account: starting it again brings the
  running one's toolbar to the front.
- Errors nothing else caught are written to `vitralis.log`, and Ctrl+C or a
  termination signal quit through the clean shutdown.
- A snapshot that can't be saved, loaded or deleted says so in the
  Snapshots window.
- Uninstalling while Vitralis runs asks to close it first, instead of
  leaving its exe behind.
- Linting, formatting and the tests with a coverage gate run in CI.
- `.python-version` pins Python 3.13, the version Vitralis is built with.

### Changed

- Undo takes back the latest stroke on whichever monitor it was drawn,
  instead of one stroke on every monitor at once.
- Assigning a shortcut another action already had moves it: the other
  action is left without one (one key on two actions worked for neither).
- A failed update check or download caused by the connection, or by
  GitHub's rate limit, is explained in words in every language instead of
  with the technical error.
- `strokes.json`, `settings.json` and the snapshots are written whole or not
  at all, so a crash can't leave half a file; strokes now carry the time
  they were drawn.
- Drawing and changing a setting never wait for the disk: `strokes.json` and
  `settings.json` are written in the background (and finished before
  Vitralis quits), and the Snapshots window lists, saves, loads and deletes
  off the UI thread, its buttons greyed out meanwhile.
- The About window, README, CONTRIBUTING and landing page name the license
  version: PayBack License (PBL) v2.0.
- A license check that fails says what failed: too many attempts (and how
  long to wait), an answer the server shouldn't give, or a license that
  couldn't be saved, instead of always blaming the internet connection.
- A download the server refuses, and a new version that can't be put in
  place, are explained in every language instead of with an English reason.
- Quitting waits at most 5 seconds for a license check under way (it was
  20), and no longer closes a connection a request is still using.

### Fixed

- Esc with the toolbar focused while drawing, panning or deleting leaves
  the mode instead of quitting Vitralis.
- The toolbar showed stroke size 5 at start while drawing 3 px wide.
- Hiding Vitralis with the focus key while a mode was on brought the
  toolbar back saying "Drawing…" with nothing to draw on.
- A drawing or snapshot that couldn't be saved failed silently; a damaged
  `strokes.json` could stop the overlay from painting. Failures are now
  logged, damaged strokes are skipped, and an unreadable file is kept as
  `strokes.json.damaged`.
- The first versions' `strokes.json` (a bare list) lost the primary
  monitor's drawings on the first save of another monitor.
- A focus shortcut the global hook didn't know (some special keys) could
  end Vitralis; such a key is now refused. Quitting no longer depends on
  the hotkey thread being alive.
- Stopping the global mouse-wheel hook could, rarely, end the process or
  hang at quit.
- The tray menu, the Settings title, the color picker's title and the
  Snapshots title were English only; an active mode's label, the
  Show/Hide overlay tooltip and the shortcuts' reset tooltips didn't
  follow a language change.
- A damaged `settings.json` entry (shortcuts or language of the wrong
  kind) could stop Vitralis from starting.
- Closing the toolbar from outside (Alt+F4, `taskkill`) left Vitralis
  running with no toolbar; it now quits cleanly.
- The log no longer holds the address of every request, which carried this
  computer's license activation id.
- Two parts of Vitralis saving settings at once no longer undo each other's
  changes, and an unreadable `settings.json` is logged instead of silently
  ignored.
- A snapshot named like a Windows device (`CON`, `NUL`, `COM1`…) couldn't be
  saved; it is now kept as `_CON`.
- While locked, the license window took the focus back every minute and
  replaced what it said about the last attempt ("That key isn't valid") with
  the opening message; a refused key also hid **Check again**.
- A `licence.dat` damaged in certain ways stopped Vitralis at every start;
  it now counts as no license, like any other damage.
- A temporary file held by another program while the license was saved
  could end the daily license checks until the next start.
- Starting a second Vitralis could delete the update the running one had
  downloaded, so **Restart to update** failed.

### Security

- `setuptools` (build only) updated past PYSEC-2026-3447 and
  GHSA-xmj3-9gf7-h52w.
- The activation id could still reach `vitralis.log` inside the reason of a
  failed license check; the address is now left out of it.
- Update checks and downloads refuse any redirect to an address that isn't
  HTTPS (only the first address was checked before).

## [1.3.0] - 2026-11-11

### Added

- Vitralis now requires a license key from Clavren (`clavren.breren.com`).
  On first start a license window asks for the key instead of showing the
  overlay; the key is bound to this computer, checked online once a day,
  and keeps working offline for up to 30 days. If the license is revoked,
  expires, is withdrawn, or needs an online check (30 days offline, or the
  clock set back), the overlay closes and the window says why, offering
  **Check again** where a check can unlock it. The saved license is
  encrypted for the Windows account (DPAPI).
- Settings → License: test or full license, valid until, works offline
  until (highlighted under 5 days), and **Check now**. All license texts
  are translated into every UI language.
- The landing page says, under the download button, that Vitralis needs a
  license key and whom to write to for one, in all eight page languages.
- Logging to `%APPDATA%\Vitralis\vitralis.log`.
- A test suite (`uv run pytest`), with a contract test against the real
  license server behind `-m live` and `VITRALIS_LICENCE_TEST_KEY`.

- GitLab and Codeberg source links next to the existing GitHub one in
  the hero CTA row, localized across all eight supported languages,
  each using its own official logo.
- When embedded in an iframe, the landing page listens for a
  `vitralis-preset` `postMessage` from `https://breren.com` and applies
  the visitor's language/theme from it on every load — lets
  `breren.com/vitralis` hand off its current language/theme every time,
  not just on first visit, without touching the URL.
- `docs/index.html` — a static landing page for GitHub Pages
  (`ran-n.github.io/vitralis`), styled with the same Gruvbox palette
  and light/dark toggle as breren.com, with a language picker
  (Galego, English, Español, Português, Français, Deutsch, 中文,
  日本語 — the app's own shipped UI languages) and a download button
  that fetches the latest GitHub release at load time so it never
  goes stale.

### Changed

- The landing page now defaults to dark mode regardless of system
  preference; the visitor's choice is remembered from the first
  toggle onward.
- The download button now sits in its own row above the source links
  and is visually larger, since it's the primary call to action; the
  GitHub/GitLab/Codeberg source links moved to a smaller row below.

### Fixed

- External links (GitHub, GitLab, Codeberg, Breren) now target `_top`
  instead of `_blank`, so when the landing page is running inside
  breren.com's iframe they break out to the same tab instead of
  attempting to load the external site framed — which those sites
  refuse, since it's a top-level navigation now, back/forward and the
  URL bar behave normally.

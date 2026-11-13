[//]: # ( ---------------------------------------------------------------------- )
[//]: # (+ Authors: 	Ran# <ran.hash@proton.me> )
[//]: # (+ Created: 	2026/08/04 12:03:36.212196 )
[//]: # (+ Revised: 	2026/11/13 20:12:34.843177 )
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

### Fixed

- The About window, README, CONTRIBUTING and landing page name the license
  version: PayBack License (PBL) v2.0.
- Two parts of Vitralis saving settings at once no longer undo each other's
  changes, and an unreadable `settings.json` is logged instead of silently
  ignored.

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

[//]: # ( ---------------------------------------------------------------------- )
[//]: # (+ Authors: 	Ran# <ran.hash@proton.me> )
[//]: # (+ Created: 	2026/08/04 12:03:36.212196 )
[//]: # (+ Revised: 	2026/08/04 12:15:27.447546 )
[//]: # ( ---------------------------------------------------------------------- )

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

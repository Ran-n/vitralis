# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- The landing page now honors `?lang=` and `?theme=` URL query
  parameters as a one-time seed for the visitor's stored preference
  (only applied when nothing is stored yet, so it never overrides an
  in-page toggle) — lets an embedding page such as `breren.com/vitralis`
  hand off its current language/theme.
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

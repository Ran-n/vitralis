[//]: # ( ---------------------------------------------------------------------- )
[//]: # (+ Authors: 	Ran# <ran.hash@proton.me> )
[//]: # (+ Created: 	2026/11/11 17:31:20.784664 )
[//]: # (+ Revised: 	2026/11/11 17:31:20.784664 )
[//]: # ( ---------------------------------------------------------------------- )

# TODO

The backlog. Each item is self-contained: reading it alone is enough to
implement it fully, without asking anything. Work top to bottom unless an item
says otherwise.

Next item number: 3

## Index

1. [Tell the user when a new version is out](#1-tell-the-user-when-a-new-version-is-out)
2. [Download and install an update from inside the app](#2-download-and-install-an-update-from-inside-the-app)

## Adding an item

- Write for someone who has never seen the conversation: what happens today,
  what should happen instead, and why each non-obvious decision was made.
- Be concrete: real file paths, names, sizes, colours, keys. No open "maybe";
  if the implementer must choose, say how to choose and how to check.
- Use the template below. Implementation is a numbered list of steps in the
  order to do them; Done when is a checklist.
- Number it with "Next item number" above, then increase that number.
- File order is priority: the first item is the next one to do.
- Numbers ascend in file order. Deleting leaves a gap; when adding at the top
  or moving an item breaks the order, renumber every item in file order (from
  the lowest number in use) and update every reference to them.
- Keep the Index in file order: one `<n>. [title](#anchor)` line per item;
  update it whenever an item is added, retitled, moved or deleted.
- Screenshots go in `docs/todo/<n>-<slug>.png`, linked from the item.
- Split anything bigger than one sitting into items that ship alone.

## Implementing an item

1. Read the whole item and every file it names; check `git status` first.
2. If the code has drifted from the item, adapt and note it; if the item
   contradicts a newer decision, ask before building.
3. Do the Implementation steps in order.
4. Write the listed tests, plus any others the change needs.
5. Lint, format, update file headers and run the full test suite until clean.
6. For visible changes, run the app and check it in the states the item names.
7. Update the listed docs; write the changelog line when committing.
8. Tick every Done when line, with evidence.
9. Delete the item, its Index line and its screenshots; add follow-up work as
   new items.

## Template

```markdown
## <n>. <short imperative title>

**Why:** what happens today and what is wrong with it.
**Goal:** the result, as the user will see it.

### Behaviour
- One bullet per case, edge cases included.

### Out of scope
- What this item deliberately doesn't change.

### Implementation
1. `<path>`: what changes and why.

### Tests
- `<test file>`: each case and what it proves.

### Docs
- `<doc file>`: what to change. Changelog: "<line>".

### Done when
- [ ] Checkable result.
```

---

## 1. Tell the user when a new version is out

**Why:** Vitralis ships as a single PyInstaller exe (`vitralis-X.Y.Z.exe`, built by `src/vitralis/build.py`) attached to the releases on GitHub, GitLab and Codeberg. Nothing inside the app says when a newer one exists, so someone running 1.3.0 keeps it until they happen to visit a forge or the landing page. This matters more since 1.3.0: a licence or server change may need a newer client, and users have no way to hear about it. This is the first half of the in-app updater; item 2 (download and install) builds on it.

**Goal:** at every start and then once a day, Vitralis asks GitHub for the latest release. When it is newer than the running version, the toolbar's Settings button gets an accent dot, the tray shows one notification **Vitralis {version} is out**, and Settings → **Updates** shows the version with **Release notes** and **Skip this version**. Everything is inline in the existing windows; no new dialog.

### Behaviour
- **When it checks:** at start, about 10 s after the overlay is up (so start-up isn't slowed), then every 24 hours while running (`UPDATE_CHECK_EVERY = dt.timedelta(hours=24)`). The last check time lives in memory only: every start checks anyway. Only while licensed (the check lives in `Session`, which only exists while the licence holds); the locked licence window doesn't check, which keeps the locked state simple.
- **Which release:** GitHub's `GET https://api.github.com/repos/Ran-n/vitralis/releases/latest` (latest non-draft, non-prerelease). Its `tag_name` (`v1.4.0`) is compared numerically with `app_version()` from `src/vitralis/version.py` (`1.10.0 > 1.9.0`). GitHub only, because all three forges carry the same releases and the landing page already reads GitHub; a failure shows in Settings.
- **Newer release found:**
  - The Settings button (`Toolbar._settings_btn`, 26×26) gets a small accent dot (`#e07020`, `BTN_CHECKED` in `src/vitralis/styles.py`), 6 px, top-right, painted on top, and its tooltip becomes "Settings · Vitralis {version} is out". The dot changes neither the button's size nor the toolbar width: the toolbar width is locked after init and must never change, and the title stays centred.
  - The tray icon shows `QSystemTrayIcon.showMessage("Vitralis", "Vitralis {version} is out", ...)` once per newly seen version per run, so a daily re-check of the same version doesn't nag.
  - Settings → **Updates** shows "Vitralis {version} is out" with **Release notes** (opens the release's `html_url` with `QDesktopServices.openUrl`) and **Skip this version**.
- **Up to date (same or older):** an older release can happen with a dev build ahead of the last tag. There is no dot and no tray message, and Settings shows "Vitralis {current} is up to date · checked {HH:MM}".
- **Skip this version:** saves the version in `settings.json` (`"updates": {"skipped": "1.4.0"}` through `SettingsManager`). The dot and tray message go away until a release newer than the skipped one appears. Settings still shows "Vitralis {version} is out (skipped)" with **Don't skip**, which clears it.
- **Check for new versions switch:** off (`"updates": {"check": false}`) means no automatic check. **Check now** still works, because the user asked for that one.
- **Check now:** dimmed with the text "Checking…" while it runs, and the result line updates when the answer arrives. It runs on a worker thread whose result returns through a queued Qt signal, the same pattern as `LicenceGate._run` in `src/vitralis/licence/gate.py`, so the UI never waits on the network.
- **Errors:** offline, timeout, HTTP error, GitHub's 403/429 rate limit (60 unauthenticated calls an hour per IP), or a malformed answer (no `tag_name`, a tag that isn't `vX.Y.Z`, JSON that won't parse). Each is logged at WARNING with the URL. Settings shows "Couldn't check for updates: {reason}" in `#ff8a65` (the error colour of `src/vitralis/licence/section.py`). There is no dot and no tray message: a failed background check isn't worth interrupting for, and the Settings line keeps it from being silent.
- **Running from source** (`getattr(sys, "frozen", False)` is false): the same notice; item 2's Install is only for the packaged exe.
- **`VITRALIS_RELEASES_URL`:** when this environment variable is set, it replaces the GitHub API URL, so tests and item 2's end-to-end check can serve their own release JSON.

### Out of scope
- Downloading and installing (item 2).
- Pre-releases or a beta channel.
- Checking from the locked licence window.
- Falling back to GitLab or Codeberg when GitHub fails.

### Implementation
1. `src/vitralis/updates/__init__.py` (new package, `metadata -c`, merge the docstring into the header): describe the updater, as `src/vitralis/licence/__init__.py` does for the licence.
2. `src/vitralis/updates/rules.py` (new, no I/O, no Qt):
   - `Version`: a frozen dataclass of three ints with `order=True`.
   - `parse_version(text) -> Version`: accepts `v1.4.0` and `1.4.0`, raises `ValueError` on anything else, including `?` (`version.UNKNOWN`).
   - `Release`: a frozen dataclass `(version: Version, page_url: str, exe_url: str | None, checksum_url: str | None)`.
   - `update_to_offer(current: Version | None, latest: Release, skipped: str) -> Release | None`: returns `latest` only when it is newer than `current` and newer than `skipped` (when `skipped` parses); when `current` is None (unknown version) it always offers.
3. `src/vitralis/updates/github.py` (new): `GitHubReleases(http: httpx.Client, url: str = RELEASES_URL)` with `latest() -> Release`.
   - Sends `Accept: application/vnd.github+json` and `User-Agent: vitralis/{app_version()}` (GitHub refuses requests without a User-Agent; reuse `USER_AGENT` from `src/vitralis/licence/server.py` by moving it to `src/vitralis/version.py`, then update the server's import, DRY).
   - Timeout 15 s.
   - Picks the assets named exactly `vitralis-{version}.exe` and `vitralis-{version}.exe.b3` (the names `build.py` and the release recipe produce).
   - Raises `ReleaseFeedError(Exception)` with a one-line reason for every `httpx.HTTPError`, non-200 status, `ValueError` or `KeyError`.
   - Logger `vitralis.updates.github`.
4. `src/vitralis/settings.py`, `SettingsManager`: add `update_check() -> bool` (default True), `set_update_check(bool)`, `skipped_version() -> str` (default ""), and `set_skipped_version(str)`, stored under `"updates"` in `settings.json`. An old `settings.json` without the key must load with the defaults.
5. `src/vitralis/updates/checker.py` (new, Qt): `UpdateChecker(QObject)`, built from a feed, a `SettingsManager`, the current version and a clock.
   - Signals: `changed(object)` (an `UpdateStatus`) and `busy_changed(bool)`.
   - `UpdateStatus`: a frozen dataclass `(latest: Release | None, offered: Release | None, checked_at: dt.datetime | None, error: str)`.
   - Methods: `check_now()` (worker thread named `vitralis-update-check`, result through a queued signal, as in `LicenceGate`) and `start()`/`stop()` (a `QTimer`: 10 s single shot, then every 24 h, skipped while the switch is off).
   - `offered` is recomputed from the live skipped setting on `skip()`/`unskip()`, without a new check.
   - INFO "version {v} is out (running {current})" is logged once per newly seen version.
   - A `ReleaseFeedError` becomes `status.error` and keeps the previous `latest`. Any other exception is logged with `logger.exception` and shown as an error too, so the UI never waits for ever.
6. `src/vitralis/updates/section.py` (new): `UpdatesSection(QWidget)`, built like `src/vitralis/licence/section.py`.
   - Rows: "Version {current}" and the result line.
   - Controls: a **Check for new versions** checkbox (`QCheckBox`, styled like the window's labels), **Check now**, **Release notes**, and **Skip this version** / **Don't skip**. Buttons with no action available are hidden or dimmed (`QPushButton:disabled` in `styles.base_btn`).
   - Add `retranslate()`.
7. `src/vitralis/settings.py`, `SettingsWindow`: take `updates: UpdateChecker | None = None` next to `licence`. When it is given, add `_add_section(inner, "Updates")` and the section before **License**, and call its `retranslate()` from `retranslate()`.
8. `src/vitralis/toolbar.py`:
   - `Toolbar.__init__` takes `updates: UpdateChecker | None = None` and passes it to `SettingsWindow`.
   - Paint the dot on `_settings_btn` with an event filter or a small subclass whose `paintEvent` draws a 6 px ellipse after the base paint, so the button's fixed size stays 26×26.
   - Connect `updates.changed` to show or hide the dot and set the tooltip.
9. `src/vitralis/tray.py`: `make_tray_icon` returns the tray as today. `Session` (step 10) connects `updates.changed` to a function that calls `tray.showMessage` once per new version.
10. `src/vitralis/app.py`, `Session`:
    - Build one `httpx.Client` and the `UpdateChecker` in `main()` (feed URL from `os.environ.get("VITRALIS_RELEASES_URL") or RELEASES_URL`).
    - `Session.start()` calls `updates.start()` and passes `updates` to `Toolbar`; `Session.stop()` calls `updates.stop()`.
    - `_shutdown` closes the update `httpx.Client` after `session.stop()`.
11. `src/vitralis/translations.py`: add every new string to all 8 non-English tables with real translations, and check that `tests/licence/test_messages.py::test_every_language_has_the_same_keys` still passes. The strings: "Updates", "Check for new versions", "Version {version}", "Vitralis {version} is out", "Vitralis {version} is out (skipped)", "Vitralis {version} is up to date · checked {time}", "Couldn't check for updates: {reason}", "Release notes", "Skip this version", "Don't skip", "Settings · Vitralis {version} is out".
12. Run `uv run ruff format` then `uv run ruff check` on the edited `.py` files and fix by hand (never `--fix`). Run `metadata -c` on new files, merging the docstring into the header, and `metadata -m` on edited ones.

### Tests
- `tests/updates/test_rules.py`:
  - `parse_version` accepts `v1.2.3` and `1.2.3`, and rejects `1.2`, `v1.2.3-rc1`, `?` and `""`.
  - `1.10.0 > 1.9.0`.
  - A Hypothesis property: round trip and tuple ordering for any three non-negative ints.
  - `update_to_offer`: newer offered; equal and older not offered; equal to skipped not offered; newer than skipped offered; current unknown offered; a malformed skipped value is ignored.
- `tests/updates/test_github.py` (respx):
  - A real-shaped answer gives the version, page and both asset URLs.
  - A release without the exe gives `exe_url=None`.
  - 404, 403, 429, malformed JSON, a missing `tag_name` and a tag `v1.2` each raise `ReleaseFeedError` with a readable reason.
  - A connection error raises `ReleaseFeedError`.
  - The User-Agent and Accept headers are sent.
- `tests/updates/test_checker.py` (offscreen `QApplication` from `tests/conftest.py`, fake feed, `wait_until`):
  - `check_now` emits busy True then False, and a status with `offered`.
  - Skip hides `offered` without a new check, and Don't skip brings it back.
  - A feed error sets `error` and keeps `latest`.
  - An unexpected exception is shown and never leaves `busy` stuck.
  - The switch off means the timer doesn't check, but `check_now` does.
  - The INFO line is logged once per new version (caplog).
- `tests/test_settings_manager.py`: the defaults; an old `settings.json` without `"updates"` loads; values round-trip through the file (monkeypatch `SETTINGS_FILE` to `tmp_path`).
- `tests/updates/test_section.py` (`ui` marker):
  - Each state builds with the right texts and enabled buttons: up to date, out, out (skipped), error, and checking (Check now dimmed).
  - The Skip and Don't skip clicks save.
  - Relabelling in Deutsch works.
- `tests/test_toolbar_update_dot.py` (`ui` marker; monkeypatch `GlobalHotkeyThread` and `GlobalMouseWheelThread` with inert stand-ins so no system hooks are installed):
  - The dot pixel is the accent colour at the button's top-right only when an update is offered.
  - The toolbar width is identical with and without the dot.
- `tests/licence/test_messages.py::test_every_language_has_the_same_keys` stays green with the new strings.

### Docs
- `README.md`: a Features bullet "Tells you when a new version is out (Settings → Updates)", and the **Updates** row described under a short "Updates" heading after **License key**.
- Changelog: "Added a notice when a newer Vitralis is out: a dot on the toolbar's Settings button, one tray message, and Settings → Updates with Release notes and Skip this version, checked at start and once a day".

### Done when
- [ ] With `VITRALIS_RELEASES_URL` pointing at a local server answering `{"tag_name": "v99.0.0", ...}`, the running app shows the dot, one tray message, and the Settings line (screenshots of the toolbar and the Settings section).
- [ ] Skip this version hides the dot, and it stays hidden after a restart (`settings.json` shows `updates.skipped`).
- [ ] With the network off, Check now shows the error line and the log has the WARNING.
- [ ] The toolbar width doesn't change with the dot (asserted in a test).
- [ ] `uv run pytest` passes, with every new string in every language.
- [ ] README and CHANGELOG are updated.

## 2. Download and install an update from inside the app

**Why:** after item 1, Vitralis says a new version is out, but updating still means downloading the new exe by hand, quitting Vitralis, and replacing the old file. Windows won't let a running exe be overwritten, so users end up with several `vitralis-*.exe` files and shortcuts pointing at the old one. Do this after item 1, which provides `Release` (with `exe_url` and `checksum_url`), `UpdateChecker`, the Updates section and `VITRALIS_RELEASES_URL`.

**Goal:** in the packaged exe, Settings → Updates (and a click on the tray message) offers **Install {version}**. One click downloads the new exe with a progress line and checks its BLAKE3 checksum. **Restart to update** then quits Vitralis cleanly, puts the new exe at the same path, and starts it, and the new version says "Updated to {version}" once.

### Behaviour
- **When install is offered:** only in the packaged exe (`getattr(sys, "frozen", False)`) and only when the release has both `vitralis-{version}.exe` and its `.b3`. Otherwise item 1's Release notes stays the only action.
- **The exe keeps its path:** the running file is `Path(sys.executable)` (the onefile exe the user started, for example `C:\Tools\vitralis-1.3.0.exe`). The new version replaces it at the same path, so pinned taskbar icons, Start-menu and desktop shortcuts keep working. The About panel shows the real version, so a file name that still says 1.3.0 is the lesser evil compared with broken shortcuts after every update.
- **Check the folder first:** create and delete `<exe dir>/.vitralis-update-test`. If that fails (for example the exe sits in `C:\Program Files`), show "Can't update {dir}: move Vitralis to a folder you can write to, or update by hand" with Release notes, and download nothing.
- **Download:** the file is saved to `%APPDATA%\Vitralis\updates\vitralis-{version}.exe.part` (`persistence.DATA_DIR / "updates"`) on thread `vitralis-update-download`, streaming with `httpx.Client.stream` in 64 KiB chunks.
  - Progress shows in the Updates section as "Downloading {version}… {percent}%", from `Content-Length`; without it, "{MB} MB".
  - Install is dimmed meanwhile.
  - Quitting Vitralis sets a stop event; the download stops and the `.part` file is deleted.
- **Verify:** compute the BLAKE3 hash of the file (`blake3`, already a dependency) and compare it with the first 64 hex characters of the `.b3` file (`b3sum` format, `"<hash>  <name>"`). On a mismatch, delete the file, log both hashes at WARNING, and show "The download is damaged (checksum mismatch): try again". On a match, rename `.part` to `vitralis-{version}.exe`.
- **Ready:** the button becomes **Restart to update**. There is no automatic restart, because a restart in the middle of a drawing would interrupt the user; they pick the moment. If Vitralis quits first, the next start finds `updates\vitralis-{version}.exe` (newer than the running version, with its checksum stored next to it in `vitralis-{version}.exe.b3` and re-verified) and offers **Restart to update** straight away.
- **Restart to update:**
  1. Rename the running exe to `<name>.old` in the same folder with `os.replace` (Windows allows renaming a running image, but not overwriting or deleting it).
  2. Move the downloaded exe to the original path with `os.replace`.
  3. Start it with `subprocess.Popen([path, "--updated", "<old version>", "--wait-pid", str(os.getpid())], creationflags=DETACHED_PROCESS)`.
  4. Quit through `Toolbar._quit()`, the same clean shutdown as Ctrl+Q: the global hooks stop, the licence checks stop, and the HTTP clients close.
  If step 2 or 3 fails, `<name>.old` is renamed back, the error is shown, and the app keeps running. The user is never left without a working exe.
- **The new version's first start** (`--wait-pid`): `main()` waits up to 30 s for that PID to exit (`OpenProcess` + `WaitForSingleObject` through `ctypes`) before building anything. Two overlays, two sets of global hooks, and two writers of `licence.dat` must never run at once. If it doesn't exit in time, log an ERROR and quit, leaving the user on the old instance.
  - Then it shows "Updated to {version}" once in the tray, deletes `<name>.old` and `updates\` on a background thread (`vitralis-update-cleanup`), and logs INFO.
  - A failed delete is logged at WARNING and retried at the next start: a leftover `.old` beside a running exe is deleted whenever its name matches `<own name>.old`.
- **Licence:** the new exe reads the same `licence.dat` (DPAPI, current user, entropy `clavren:vitralis`), so it starts licensed without asking for the key again. Confirm this in Done when.
- **Running from source:** no Install, only Release notes (item 1).

### Out of scope
- Updating a source checkout, installers (MSI/MSIX), code signing, delta updates.
- Updating without the user clicking.
- Changing the release file names (`vitralis-{version}.exe` stays as `build.py` makes it).

### Implementation
1. `src/vitralis/updates/download.py` (new): `download_release(http, release, target_dir, progress, stop) -> Path`. In order: stream to `.part` with the stop event, fetch the `.b3`, verify, rename. Every failure is raised as `UpdateError(Exception)` with a user-facing reason, and `.part` is removed in `finally`. Logger `vitralis.updates.download`.
2. `src/vitralis/updates/install.py` (new, Windows):
   - `can_write(folder) -> bool`.
   - `swap_and_start(running: Path, new: Path, old_version: str, pid: int) -> None`: the rename, move and Popen of Behaviour, with rollback, raising `UpdateError`.
   - `wait_for_exit(pid, timeout_s) -> bool`.
   - `clean_leftovers(running: Path, updates_dir: Path) -> None`.
   - `pending(updates_dir, current: Version) -> Path | None`: a prepared newer exe whose `.b3` still matches.
3. `src/vitralis/updates/checker.py`: add the install state machine to `UpdateChecker`: `idle | downloading(percent) | ready(path) | failed(reason)`.
   - `install()` runs on its own thread with a queued signal.
   - `restart_to_update(quit_app)` calls `swap_and_start`, then `quit_app`.
   - On start, `pending()` sets `ready`.
   - `stop()` also sets the download's stop event.
   - Every state change is logged at INFO.
4. `src/vitralis/updates/section.py`: show **Install {version}** / "Downloading…%" / **Restart to update** / the failure line according to the state, dimming buttons while busy.
5. `src/vitralis/app.py`, `main()`:
   - Parse `--updated <version>` and `--wait-pid <pid>` from `sys.argv` (with `argparse.parse_known_args`, so Qt's own arguments pass through) before creating `QApplication`.
   - With `--wait-pid`, call `wait_for_exit` first.
   - With `--updated`, show the tray message after `Session.start()` and run `clean_leftovers` on the cleanup thread.
6. `src/vitralis/tray.py` / `Session`: a click on item 1's tray message (`QSystemTrayIcon.messageClicked`) opens Settings at the Updates section.
7. `src/vitralis/translations.py`: add the new strings to all 8 non-English tables: "Install {version}", "Downloading {version}… {percent}%", "Downloading {version}… {mb} MB", "Restart to update", "Can't update {dir}: move Vitralis to a folder you can write to, or update by hand", "The download is damaged (checksum mismatch): try again", "Couldn't install the update: {reason}", "Updated to {version}".
8. Run `ruff format` and `ruff check` (fix by hand), and `metadata -c`/`-m` on every touched file.

### Tests
- `tests/updates/test_download.py` (respx, real bytes in `tmp_path`):
  - Happy path: the file is in place with its `.b3`, and the progress callback values are right.
  - No `Content-Length` reports MB.
  - A checksum mismatch deletes the file and raises.
  - A truncated stream raises with no file left.
  - The stop event mid-stream leaves no `.part`.
  - A `.b3` in `"<hash>  <name>"` format parses (regression).
- `tests/updates/test_install.py` (`tmp_path` folders, fake Popen):
  - A successful swap: the new bytes at the original path, `.old` holds the old bytes, and Popen got `--updated` and `--wait-pid`.
  - Popen raising: `.old` is renamed back and the original bytes are at the path.
  - The move refused (`PermissionError` via monkeypatch): the original is untouched.
  - `can_write` is false on a read-only folder.
  - `pending` finds a valid prepared exe and ignores one whose `.b3` doesn't match or that isn't newer.
  - `clean_leftovers` deletes `.old` and `updates\`, and logs a failure without raising.
  - `wait_for_exit` returns True for an exited PID (a short-lived `subprocess`) and False on timeout.
- `tests/updates/test_checker.py`:
  - The install state sequence.
  - `restart_to_update` calls the swap before `quit_app` (order checked).
  - Install is not offered when not frozen or without `.b3`.
  - `stop()` during a download leaves no `.part`.
- `tests/test_app.py`:
  - `--wait-pid` waits before building anything, and quits when the PID never exits.
  - `--updated` shows the tray message once and starts the cleanup.
- `tests/updates/test_section.py`: each install state builds with the right button texts and enabled states.
- `tests/licence/test_messages.py::test_every_language_has_the_same_keys` stays green.

### Docs
- `README.md`: an "Updating" paragraph under the item 1 heading: Install, the checksum, Restart to update, the same path being kept, what happens on failure, and the writable-folder requirement.
- `CONTRIBUTING.md`, Submitting Changes: how to check an update end to end. Build version N and N+1 (`uv run build` after `uv version`), serve a release JSON for N+1 through `VITRALIS_RELEASES_URL`, install from N, and confirm N+1 starts licensed and `.old` is gone.
- Changelog: "Added installing a new version from inside Vitralis: Install downloads and checks it, Restart to update replaces the exe at the same path and starts the new version, going back to the old one if anything fails".

### Done when
- [ ] On real packaged builds N and N+1, updating through `VITRALIS_RELEASES_URL` works end to end: N+1 says "Updated to …", starts licensed without asking for the key, sits at the original path, and `.old` and `updates\` are gone.
- [ ] Only one Vitralis process is running after the update (checked in Task Manager or with `Get-Process vitralis*`).
- [ ] Changing one byte of the served exe gives the checksum error, and nothing is swapped.
- [ ] With the exe under a read-only folder, the not-writable message shows without downloading.
- [ ] Quitting during a download leaves no `.part` file.
- [ ] `uv run pytest` passes, with every new string in every language.
- [ ] README, CONTRIBUTING and CHANGELOG are updated.

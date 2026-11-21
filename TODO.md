[//]: # ( ---------------------------------------------------------------------- )
[//]: # (+ Authors: 	Ran# <ran.hash@proton.me> )
[//]: # (+ Created: 	2026/11/11 17:31:20.784664 )
[//]: # (+ Revised: 	2026/11/21 18:29:12.295783 )
[//]: # ( ---------------------------------------------------------------------- )

# TODO

The planned work. Each item is self-contained: reading it alone is enough to
implement it fully, without asking anything. Work top to bottom unless an item
says otherwise. Ideas not planned yet live in `BACKLOG.md`.

Next item number: 7

## Index

- [4. Check the leaked bounty_board key is dead and decide on the forge purge](#4-check-the-leaked-bounty_board-key-is-dead-and-decide-on-the-forge-purge)
- [5. Audit the whole history for leaked secrets and personal data](#5-audit-the-whole-history-for-leaked-secrets-and-personal-data)
- [6. Check the project against the global standards and file the gaps](#6-check-the-project-against-the-global-standards-and-file-the-gaps)

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
- Keep the Index in file order: one `- [<n>. title](#anchor)` line per item;
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
   new items (here if it's planned, in `BACKLOG.md` if not).

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

## 4. Check the leaked bounty_board key is dead and decide on the forge purge

**Why:** until 2026-11-15, `OTHER_KEY` in `tests/licence/fakes.py` was bounty_board's real Clavren test key, added in
"[A] require a clavren licence key" (2026-11-11). The history was rewritten that day (`main` became `0ff40df`; see the
project memory `project_history_rewrite.md`), but this repo is public: GitHub, GitLab and Codeberg still serve the
old commits by hash, and GitHub's public events feed lists those hashes, so the key is still readable. Revoking it on
Clavren (Clavren's TODO item 24, done by the user on the admin dashboard) makes the old commits harmless; nothing
else leaked here.
**Goal:** the key in the old commits is dead, and the forge purge is either requested or knowingly skipped.

### Behaviour
- The old key is refused by Clavren (`licence_revoked` or `invalid_key`).
- vitralis' own tests are unaffected: they use the fakes `BRN-79YN-44XQ-W025-377Z` and `BRN-2222-3333-4444-5555`.

### Out of scope
- Revoking the key and issuing a new one (Clavren's item 24; bounty_board seals the new one). bounty_board itself.

### Implementation
1. Ask the user whether Clavren's item 24 is done (use AskUserQuestion). If not, stop here: the item waits for it.
2. Check the old key is refused: the user validates it, or a validation from bounty_board's session; never write the
   key into this repo.
3. Purge: with the key dead, the old commits hold nothing else secret, so a purge is optional. Ask the user
   (AskUserQuestion): skip it, or purge. If purge: write the GitHub request for the user to send
   (support.github.com, "Removing sensitive data": repo `Ran-n/vitralis`, history rewritten 2026-11-15, the old
   commits after `8dbef6d` are unreachable, please garbage-collect and drop cached views; give one old hash from
   `gh api repos/Ran-n/vitralis/events`). Codeberg needs no request: delete and recreate the repo by
   `~/.claude/memory/feedback_codeberg_purge.md`. GitLab free accounts have no tickets; the only self-service fix
   is deleting and recreating the project, which loses release dates.
4. Record the outcome in the project memory `project_history_rewrite.md`.

### Tests
- None: no code changes.

### Docs
- None. Changelog: none.

### Done when
- [ ] The old key is confirmed refused.
- [ ] The purge is done (GitHub request given to the user, Codeberg recreated) or the user chose to skip it.
- [ ] The project memory records both.

## 5. Audit the whole history for leaked secrets and personal data

**Why:** on 2026-11-15 an audit of bounty_board found, in commits already pushed: a real Clavren licence key in a
test file (`tests/licence_fakes.py`), from where it had been copied into vitralis, a public repo; the licence key the
user handed to an avalio-lite session, committed into its tests (whole, and half of it in another test); two
screenshots under `docs/todo/` showing the user's own player card (full name, e-mail, phone, birth date, player ID)
and their local stores, which gives away where they live; real names, a username, a player ID and a Telegram chat ID
used as test data; and the Windows user folder in paths written into `TODO.md`. The leak-scan git hooks only see new
commits, and no text scanner reads pixels, so none of this was caught. This repo has never been audited the same way.

**Goal:** no commit, tag, branch or release file of this repo, on any forge, holds a secret (key, token, password,
private key, licence key, chat or account ID) or the user's personal data (legal name outside `CONTRIBUTORS`,
e-mail, phone, birth date, address or anything that locates their home, player or account IDs, the Windows user
folder name). Anything found is gone from history, rotated if it was a secret, and purged from the forges.

### Behaviour
- The audit covers every branch and tag, every file type (images and PDFs looked at by eye) and every release asset
  built from the tree (source archives such as `.tar.gz` ship the tests).
- A finding that is a false positive is recorded, not deleted: a gitleaks fingerprint in `.gitleaksignore` with a
  comment saying what it is, or a `!regex` line in the ```` ```leak ```` block of
  `~/.claude/memory/reference_leak_terms_private.md` (then `python ~/.claude/bin/secrets.py seal`) when the same
  harmless value recurs across projects.
- A real finding in the current files is replaced by a fake that keeps the tests meaningful: licence keys by
  Clavren's published test vector `BRN-79YN-44XQ-W025-377Z` or `BRN-2222-3333-4444-5555`; names, usernames and IDs
  by made-up ones (`Alba`, `Lago Abad`, `·Estrela·`, `0000123456`); e-mails by `@example.com` or `.test`
  addresses; user paths by `~\...`; screenshots retaken with demo data.
- A real finding in history is rewritten out (step 8), so it was never committed as far as anyone can see.
- A leaked secret is also rotated: replaced at its service and the old one revoked. Personal data can't be rotated,
  so the forges must purge it before the repo is (or stays) public.
- Nothing personal of the user's is ever sent to an outside service while doing this, except the support requests
  of step 12, which name only the repo and commit hashes.

### Out of scope
- Fixing anything that isn't a leak (other items cover code quality and standards).
- Other repositories: each has its own copy of this item. Work inside this repo only.

### Implementation
1. Note each remote's visibility: `gh repo view Ran-n/<repo> --json visibility`, `glab api projects/Ran-n%2F<repo>`
   (`visibility`), and Codeberg's `GET /api/v1/repos/ran-n/<repo>` (`private`; token in
   `~/.claude/memory/reference_codeberg_token.md`). A public repo makes every finding urgent.
2. Scan all history with the hook's own checks (its rules, the personal terms and gitleaks):
   `python ~/.claude/bin/leak_history.py` from the repo root. It lists each distinct finding with its first
   commit, then every image path ever committed.
3. Scan the current files too, including uncommitted ones:
   `gitleaks dir <folder> --config ~/.claude/hooks/gitleaks.toml --redact` for each source, test, docs and script
   folder (not `.venv`, `build`, `target`, `node_modules`, which are ignored).
4. Look at every image, PDF and other binary ever committed, every version: list them with
   `git rev-list --all --objects`, write each blob out with `git cat-file blob <id> > <scratch file>` into the
   session scratchpad, and open it. Flag real names, e-mails, phones, IDs, chat IDs, tokens, addresses, a map or a
   list of nearby places centred on home, file paths with the user folder, and window titles or notifications
   showing accounts. Delete the scratch copies afterwards.
5. Grep the history for the shapes no rule knows, from the repo root:
   `git log --all -p | grep -E "BRN-[0-9A-Z]{4}-|chat_id|user_id|bandai|@gmail|C:\\\\Users\\\\"`, and for any real key in
   `~/.claude/memory` or `~/.claude/project-memory` (the sealed `reference_*` files), check that no part of it
   (any two consecutive groups) appears: a test of a "mistyped" key once held half a real one.
6. Check the release assets on every forge (`gh release download`, `glab release download`, Codeberg's release
   API) the same way: unpack each source archive and grep it; binaries without tests need no check.
7. Triage every finding into false positive or real, with the reason, and record the false positives as the
   Behaviour section says. Commit nothing yet.
8. For real findings in history: rewrite it on a copy, never in the working clone.
   a. Ask any other Claude session working in this repo (`ListAgents`, then `SendMessage`) to pause commits and
      pushes, and wait for its reply.
   b. Make a fresh bare copy: `git init --bare -b main <scratch>/orig.git`, copy `.git/objects` into it
      (`robocopy <repo>\.git\objects <scratch>\orig.git\objects /E /MT:16`, much faster than a clone on a slow
      disk), and point `main`, the other branches to publish and every tag at the clone's values with
      `git update-ref`. Leave tool refs such as `refs/codex/...` out. Copy it again to `<scratch>/new.git`.
   c. In `new.git`, run `git filter-repo --replace-text <file>` (lines `<real>==><fake>`; for one line that must
      stay, swap it to a placeholder first and back last) and/or `--strip-blobs-with-ids <file>` for images. An
      image can sit under several names: strip it by blob id, not by path.
   d. `python ~/.claude/bin/resign_rewritten.py <scratch>/new.git <scratch>/orig.git main [other branches]`: commits
      the filter didn't change stay the original objects with their original signatures (even ones made with an
      older GPG key); changed ones are re-made with the same dates and messages and signed only if they were
      signed. Then `git -C new.git repack -a -d`, delete `new.git/objects/info/alternates`,
      `git reflog expire --expire=now --all` and `git gc --prune=now`.
   e. Verify before pushing: the finding is gone (`git log --all -S<value>` is empty; `git rev-list --all
      --objects` has no stripped blob); `git log --format='%G?|%GK|%an|%ae|%ad|%cn|%ce|%cd|%B' --date=raw` is
      identical between orig and new once hashes are masked; tags' tagger, date and message are identical;
      `git diff --stat <orig main> <new main>` (with `GIT_ALTERNATE_OBJECT_DIRECTORIES` pointing at orig) shows only
      the scrubbed lines; `python ~/.claude/bin/leak_history.py` inside `new.git` is clean.
   f. Check every remote still has the `main` you copied (`git ls-remote`); if one moved, start again from b.
   g. GitLab protects `main` against force pushes: `glab api -X PATCH projects/Ran-n%2F<repo>/protected_branches/main
      -f allow_force_push=true`, push, then the same call with `false`. Push from `new.git` to every remote:
      `git push --force <url> refs/heads/main 'refs/tags/*'` (the global hooks scan the push; never bypass them).
      Check with `git ls-remote` that each forge now matches.
   h. Move the working clone onto the new history without touching uncommitted work:
      `git fetch <scratch>/new.git '+refs/heads/main:refs/rewritten/main' '+refs/tags/*:refs/tags/*'`,
      `git reset --mixed <new main>`, `git checkout -- <each file the rewrite changed and you didn't edit>`, update
      every `refs/remotes/<remote>/main`, delete `refs/rewritten/main`, then `git reflog expire --expire=now --all`
      and `git gc --prune=now`. Tell the paused session it can resume and that every hash after the first changed
      commit is new.
9. Rebuild every release asset that was built from an old tree and held a finding (source archives:
   `git archive <tag> | tar -x`, then the project's build, e.g. `uv build --sdist`), write its `.b3`, and replace
   the file on every forge without touching the release's date or notes: `gh release upload <tag> --clobber`;
   GitLab: upload with `curl -H "Authorization: Bearer $(glab config get token --host gitlab.com)" -F file=@...`
   to `projects/<id>/uploads`, swap the release link, then delete the old upload
   (`DELETE projects/<id>/uploads/<secret>/<filename>`); Codeberg: delete the asset, upload it again under the
   same name.
10. Rotate each leaked secret at its service (a Clavren licence key: revoke it and issue a new one in the Clavren
    dashboard, which only the user can sign in to, so ask them) and seal the new one in this project's memory
    (a `reference_*_keys.md` or `*_secret.md` file, sealed with `python ~/.claude/bin/secrets.py seal`).
11. GitLab keeps the old objects: delete the scrubbed blobs with the GraphQL mutation
    `projectBlobsRemove(input: {projectPath: "Ran-n/<repo>", blobOids: [...]})` (the ids are every blob in the old
    history that the new one lacks), delete the pipelines of old commits
    (`DELETE projects/<id>/pipelines/<id>`, they pin old commits), then
    `POST projects/<id>/housekeeping?task=prune`. Check a removed blob with `GET projects/<id>/repository/blobs/<id>`;
    if it is still served a day later, add GitLab to step 12.
12. GitHub (and GitLab if needed) keeps serving the old commits by hash: write a support request naming the repo,
    its visibility, the current `main`, the old heads and the scrubbed blob ids, asking them to purge cached views
    and unreachable objects; the user sends it from their account. Codeberg: no request; delete and recreate the
    repo by the steps in `~/.claude/memory/feedback_codeberg_purge.md` (snapshot settings and releases, check
    nothing unrecoverable exists, name the repo and get the user's yes right before the delete, push the branch and
    tags, recreate each release on its tag oldest first so the dates come back, check the old objects answer 404).
13. Record the outcome in this project's memory (`project_history_rewrite.md`, indexed in its `MEMORY.md`): what was
    found, where, what replaced it, the new `main`, and what is still pending.

### Tests
- No code changes, so no unit tests. Each check is evidence instead:
  - `python ~/.claude/bin/leak_history.py` exits 0 on the final history.
  - `gitleaks dir` reports nothing on every folder.
  - Every committed image has been opened and noted as clean or removed.
- If the rewrite changed test files, run the project's full test suite on the new working tree: green.

### Docs
- `CHANGELOG.md` under `[Unreleased]`, **Security**: "Removed leaked <kind> from the repository history" (no value).
- `.gitleaksignore` comments for each false positive.

### Done when
- [ ] Every remote's visibility is noted.
- [ ] `leak_history.py`, `gitleaks dir` and the grep of step 5 report no real finding; false positives are recorded
      with a reason.
- [ ] Every image and PDF ever committed was looked at.
- [ ] Every real finding is gone from history on every forge (`git ls-remote` matches the new history) and from
      the release assets, with dates, messages, tags and signatures as before.
- [ ] Every leaked secret is rotated (or the user has been asked to), and the new one is sealed.
- [ ] GitLab's old blobs are deleted or a request is written; GitHub's support request is written; Codeberg's repo is
      recreated (old objects 404, every release back with its date).
- [ ] The working clone sits on the new history with uncommitted work intact; other sessions were told.
- [ ] The project memory records the result.

## 6. Check the project against the global standards and file the gaps

**Why:** the global rules in `~/.claude/memory/` (indexed in `~/.claude/memory/MEMORY.md`) have grown: every app
now needs an in-app updater with signed releases, an About section, a portable build and an installer for each
platform, a README laid out as a landing page, and code that follows SOLID and the design patterns. Projects
written before a rule existed don't follow it: Orin, for one, wasn't following the design patterns. This repo has
not been checked against the current rules, so its gaps are unknown. Do this after item 5, so no work starts on a
history that may still be rewritten.

**Goal:** a written verdict for every global rule (follows it, not applicable and why, or a gap), and every gap
filed as its own item in this `TODO.md`, each small enough to ship alone, ordered by importance. This item only
audits and files; the filed items do the work.

### Behaviour
- Each rule is judged against the code as it is now: read the code, run the app or the tests where that is the only
  way to know.
- A rule that doesn't fit this kind of project (a library has no updater, a docs or assets repo has no build) is
  marked not applicable, with the reason.
- When this project deliberately differs from a rule, and the project spec (`project_spec.md` in its memory) or a
  decision records why, that is a documented exception, not a gap; when nothing records it, ask the user with
  AskUserQuestion whether it is an exception or a gap.
- Each gap becomes one item written by the `/todo` writing rules (Why, Goal, Behaviour, Out of scope,
  Implementation, Tests, Docs, Done when), with the rule's file named in its Why.

### Out of scope
- Fixing the gaps here: each filed item fixes its own.
- Changing a global rule. If a rule looks wrong for this project, raise it with the user instead of bending it.
- Other repositories: each has its own copy of this item.

### Implementation
1. Read `~/.claude/memory/MEMORY.md` and every rule file it lists under Session Behaviour, Git & Version Control,
   Python Projects (when this is a Python project), Repository Setup, Code Quality, API Design (when it has an
   API) and UI (when it has a UI), plus this project's `project_spec.md`.
2. Check the project, rule by rule, and write the verdict in a table in this item's working notes (not committed):
   - **App standards:** `feedback_app_consistency.md`, `feedback_universal_behaviours.md` (clean shutdown on every
     quit path), `feedback_about_section.md`, `feedback_in_app_updater.md` (GitHub + GitLab check, minisign-format
     signature + BLAKE3 proof before download, self-replace, restart, signing tool, tests, bridge from an older updater),
     `feedback_build_matrix.md` (portable + installer per platform, names `<app>-<version>-<target>-portable|setup`,
     `.b3` + `.minisig`, tag-driven draft release, per-user installer and its test),
     `feedback_versioned_build_filenames.md`, `feedback_releases.md`, `feedback_persist_all_settings.md`.
   - **Repository:** `feedback_new_repo_scaffold.md`, `reference_license.md` (PayBack License, never MIT or Apache),
     `reference_readme_layout.md`, `reference_contributing_layout.md`, `reference_contributors_layout.md`,
     `feedback_changelog.md`, `feedback_site_organization.md`, `feedback_git_remotes.md` (`main`, all three forges
     over SSH).
   - **Code:** `feedback_clean_code.md` (SOLID, GoF patterns where they fit, DRY, files under about 200 lines,
     functions under about 20; list the worst offenders with their sizes), `feedback_source_organization.md`,
     `feedback_logging.md`, `feedback_no_silent_failure.md` (grep for bare `except`, swallowed errors),
     `feedback_parallel_code.md`, `feedback_regression_safety.md`, `feedback_database_bcnf.md`,
     `feedback_no_future_imports.md`, `feedback_file_headers.md`, `feedback_python_projects.md` and
     `reference_pyproject_scaffold.md` (ruff, line length 120), `reference_preferred_stack.md`.
   - **Tests:** `feedback_tests.md` (every type in its checklist, coverage gate), `feedback_tests_rendered_ui.md`,
     `feedback_ui_tests_no_input_hijack.md`, `feedback_ui_tests_hidden.md`; run the suite with coverage and note
     the figure.
   - **UI and text:** `feedback_i18n_completeness.md`, `feedback_ui_inline_editing.md`,
     `feedback_ui_disabled_buttons.md`, `feedback_ui_cta_hierarchy.md`.
3. For each gap, add an item at the end of this file with `/todo` (one rule per item, or one area of the code per
   item for a large refactor), in this order: security and data loss first, then the updater and releases, then
   tests, then code structure, then docs and layout. Put the rule file in each item's Why.
4. Reply to the user with the table's gaps and the new item numbers.

### Tests
- None for this item: it changes no code. Each filed item lists its own tests.

### Docs
- None for this item. Changelog: none (an audit changes nothing).

### Done when
- [ ] Every rule file in the groups of step 2 has a verdict: follows, not applicable (with reason), exception (with
      where it is recorded) or gap.
- [ ] Every gap is filed as its own item in this `TODO.md`, in the order of step 3, with the Index updated.
- [ ] The test suite's coverage figure is noted.
- [ ] The user has the list of gaps and item numbers.

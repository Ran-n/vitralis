[//]: # ( ---------------------------------------------------------------------- )
[//]: # (+ Authors: 	Ran# <ran.hash@proton.me> )
[//]: # (+ Created: 	2026/11/15 14:27:08.591673 )
[//]: # (+ Revised: 	2026/11/15 16:41:05.775016 )
[//]: # ( ---------------------------------------------------------------------- )

# Design decisions

Why Vitralis does some things the way it does. Each record says what the problem was, what was decided, how it
compares with common practice, and what follows from it.

## 1. A self-updating exe, proven by a release-key signature

**Context.** Vitralis ships as one Windows exe, portable or installed per user. Users should get new versions
without reinstalling, and every app of its family updates the same way. A download from a forge can be
swapped by whoever controls the forge account, the file host or the network in between; a checksum served
next to the file proves nothing about who made it.

**Decision.** The updater (`src/vitralis/updates`) asks GitHub and GitLab at the same time for the latest
release and takes the newest answer, so one forge being down can't hide a release. A release offers the
portable exe `vitralis-<version>-windows-x86_64.exe` with a `.b3` (BLAKE3) and a `.sig`: an Ed25519 signature
by the release key over `vitralis-release-v1`, the version, the file name and the hash. Before one byte of
the exe is asked for, the `.sig` must check out against one of the two public keys built into Vitralis (the
signing key and a backup kept apart). The exe is then streamed, capped at 200 MiB, 60 s without data and 30
minutes in all, hashed as it comes, compared with the `.b3`, put at the running exe's path (the running one is
moved aside, as Windows allows) and started; Vitralis quits cleanly first. Only release builds, which have
their target compiled in (`VITRALIS_RELEASE_TARGET` at build time), check at all; a build from source never
does. Releases are built and attested by CI, and signed by hand from the tag's checkout: the key never goes
near CI or a forge.

**Compared with common practice.** Most desktop apps rely on an operating-system code-signing certificate
(Authenticode) or an update framework with its own signing (Squirrel, WinSparkle, TUF). A code-signing
certificate costs money every year and proves only who bought it; the frameworks bring an installer format and
a server layout of their own. Signing the version and the file name along with the hash (as TUF does) stops a
genuine older build, or another file of the release, being served as the new one, which a hash-only signature
allows.

**Consequences.**
- The first download from a release page isn't covered by the signature, only updates are; there is no
  Authenticode signature, so SmartScreen may warn on first run.
- There is no rollback.
- A forge reporting a fake higher version wins the comparison; its download then fails the signature check and
  the error is shown, rather than falling back to the other forge.
- The build attestation proves a file came from the release workflow, not that the workflow was honest;
  reproducible builds would close that.
- Losing the signing key means signing the next release with the backup and shipping a new pair at once;
  losing both means everyone downloads the next version by hand.

## 2. About is its own window, not a section of Settings

**Context.** Every app of the family puts its About section inside Settings where it has one.

**Decision.** Vitralis keeps About as its own panel beside the toolbar (the ⓘ button), with everything the
section holds elsewhere: the app and its description, version and build, author, the publisher Breren with its
logo and site, the licence with the third-party licences, and the links to the source, the releases, the
changelog and the issue tracker.

**Why.** The Settings window has no scrolling and is already about 1,050 pixels tall (shortcuts, language,
updates, licence); another section would push it past a 1080p screen. Its own panel is the closest equivalent,
and it is reached the same way as before.

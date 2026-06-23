# Self-Update System — Design (Desktop / PC version)

**Date:** 2026-06-23
**Scope:** `main` branch (desktop app) only. Nothing here touches the `device` branch.

## Goal

When a newer version is released on GitHub, the app notices, notifies the user,
and — on the user's consent — downloads the right installer for their OS, applies
it, and relaunches into the new version. One click: "Update & Restart."

## Founding-constraint tension

The app's promise is "fully offline: no network, cloud, accounts, telemetry."
An update check needs the network. We honor the promise by:

- **No accounts / no token.** The repo is public, so the GitHub
  `releases/latest` endpoint is read anonymously.
- **No telemetry.** The check is a plain GET; nothing about the user is sent.
- **Network touched in exactly one place** (`rsvp/update/`), so the rest of the
  app stays offline by construction.
- Auto-check is **on by default** (user's decision) with a **Settings toggle**
  to turn it off. A check never blocks or interrupts reading.

## Architecture

New self-contained package; all networking and the messy per-OS apply step live
behind clean interfaces so the pure logic is fully unit-testable.

```
rsvp/update/
  version.py     # parse_version() + is_newer() — "1.0.0" vs tag "v1.1.0"
  release.py     # Release dataclass; ReleaseProvider interface.
                 #   GithubReleaseProvider = real; FakeProvider = tests.
  assets.py      # choose_asset(release, system) -> Asset|None  (OS/arch match)
  downloader.py  # download(url, dest, progress) — streamed, size-checked
  apply.py       # Applier interface + WindowsApplier / MacApplier / LinuxApplier
                 #   + relaunch. Chosen by platform; dev/source mode falls back.
  updater.py     # Updater: orchestrates check -> compare -> download -> apply.
                 #   The only module that reaches the network / filesystem-apply.
```

### Data flow

```
launch (auto-check on)        Settings: "Check for updates"
        \                      /
         v                    v
   Updater.check()  ->  GitHub releases/latest JSON
        -> Release(version, notes, assets[])
        -> is_newer(current, release)?  no -> (silent on auto; "up to date" on manual)
                                        yes -> UpdateDialog(version, notes)
   user: "Update & Restart"
        -> choose_asset(release, this_os) -> Asset
        -> downloader.download(asset.url, tmp, progress)   [worker thread]
        -> Applier.apply(tmp) -> relaunch
```

## UI integration (`rsvp/ui/`)

- **`update_dialog.py`** — a styled `tk.Toplevel` (app dark palette, accent
  button) showing `current → new`, scrollable release notes, and
  **"Update & Restart" / "Later."** During apply it swaps to a progress bar.
  On failure: clear message + "Open Releases page" fallback. Isolated from the
  canvas renderer.
- **Launch:** `root.after(~1500ms, _auto_check_updates)` — only if auto-check is
  on AND this version hasn't already been auto-notified (`notified_version`),
  so it pops at most once per release. Manual check always shows a result.
- **Settings menu** gains two rows:
  - `Check for updates` (manual trigger; always gives feedback)
  - `Auto-update:  On/Off`
- **About** already shows `Version`; unchanged.

## Settings / store

Add to defaults in `RsvpApp.__init__`:
- `auto_update: bool = True`
- `notified_version: str = ""`  (last version we auto-popped, to avoid nagging)

## Threading

tkinter is single-threaded. The check and the download run on a worker thread;
all UI updates are marshalled back via `root.after`. The reading loop is never
blocked.

## Per-OS apply (the one part needing a live release to fully verify)

- **Linux (AppImage):** app's own path from `$APPIMAGE`; download new AppImage to
  temp, replace the file, `chmod +x`, `os.execv` to relaunch.
- **Windows (NSIS):** download `Setup.exe`; `subprocess.Popen([setup, "/S"])`;
  app exits so the installer can replace files; installer relaunches the app.
- **macOS (DMG):** download `.dmg`; detached helper mounts it (`hdiutil`),
  replaces the `.app`, detaches, relaunches via `open`. Gatekeeper may show one
  prompt (unsigned) — documented, not hidden.
- **Dev / source mode** (not frozen, no installer): self-apply isn't possible;
  fall back to opening the Releases page.

## Edge cases

- Offline / network error: auto-check fails silently (log only); manual check
  says "Couldn't reach the update server — you may be offline." 5s timeout.
- No matching asset for this OS: fall back to opening the Releases page.
- Already latest / equal / older remote: no prompt.
- Interrupted download: stays in a temp file; only applied once complete and
  size-checked. Never a half-applied install.
- Never interrupts an active RSVP session.

## Code-signing note

Installers aren't signed/notarized yet. Self-update works unsigned, but the OS
may show one Gatekeeper (macOS) / SmartScreen (Windows) prompt when the
downloaded installer runs — the same prompt a manual download triggers. The
mechanism is built signing-ready.

## Testing (TDD)

- **Pure unit:** `parse_version` / `is_newer` (1.0.0 vs v1.0.0 vs 1.2.0 vs 0.9
  vs pre-release); `choose_asset` per OS name patterns; release-JSON parsing
  incl. malformed/empty/no-assets.
- **Orchestrator:** inject Fake provider + Fake downloader + Fake applier; assert
  check → download → apply → relaunch transitions and every failure branch
  (offline, no asset, download error).
- **Real per-OS apply:** behind the `Applier` interface; exercised with fakes in
  CI; the live apply verified manually against an actual test release.

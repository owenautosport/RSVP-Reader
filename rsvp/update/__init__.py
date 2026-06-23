"""Self-update for the desktop app.

The ONLY package in the project that reaches the network. Everything here is
desktop-only — the pocket device (the ``device`` branch) stays fully offline and
ships no updater. The repo is public, so the GitHub Releases endpoint is read
anonymously: no token, no account, no telemetry.
"""

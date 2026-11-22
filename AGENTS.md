# Customization Rules & Guidelines: Kaffeine DVR

- **Honesty & Transparency**: Never lie, invent unverified theories, or state hypothetical guesses as confirmed facts. If a root cause is unknown or unverified, state the uncertainty directly and stick strictly to verified empirical evidence.
- **Never Use Emojis**: Never use emojis in responses, code comments, documentation, commit messages, or anywhere else unless explicitly requested by the user.
- **No Hardcoded User Paths**: All applications, scripts, configurations, and service files must be written without hardcoded user paths (e.g., avoid /home/<user>, /Users/<user>, or C:\Users\<user>). Always use dynamic environment- or runtime-resolved paths (such as `Path.home()`, `os.environ.get("HOME")`, or relative paths from the project base directory).
- **Never Search Over SMB / Network Mounts**: Never execute recursive searches (e.g., `find`, `grep`, `du`, or directory indexing) over SMB, CIFS, NFS, or any network-mounted filesystems (such as `/mnt/HD8TB` or remote shares) unless specifically instructed by the user.
- **Never Suggest or Run sudo dnf upgrade on Nobara**: Never suggest, propose, or execute `sudo dnf upgrade`, `sudo dnf5 upgrade`, or direct package manager upgrades on this system. Nobara relies strictly on `nobara-sync` to safely manage packages, kernel patches, and staging.
- **Never Create Releases on General Updates**: When asked to update, push, commit, or sync code to GitHub, only perform standard git operations (stage, commit, push to remote branch). Never create a GitHub release (`gh release create`), publish release notes, or create new version tags unless the user explicitly and specifically instructs to create or publish a release.
- **Release Title Naming Convention**: When explicitly instructed to create or edit a GitHub release, the release title/name must strictly be the application name followed by the version number (e.g., `Kaffeine DVR <version>` such as `Kaffeine DVR v0.5.1`), without feature descriptions, subtitles, or suffixes.
- **Release Versioning Scheme**:
  - For versions up to `v0.7.x`: Increment the third digit (patch version) by 1 each time. When the third digit exceeds 9 (e.g. after `v0.5.9`), roll over to 0 and bump the second digit by 1 (e.g. `v0.5.9` -> `v0.6.0`).
  - Once reaching `v0.8.0`: The third digit increments up to 15 (e.g. `v0.8.0` through `v0.8.15`) before rolling over to `v0.9.0`.
  - At `v0.9.x`: The third digit increments indefinitely (`v0.9.0`, `v0.9.1`, `v0.9.2`, ...) until instructed otherwise.
- **No AI Mockup Illustrations or Simulated Screenshots**: Never generate fake AI mockup illustrations, simulated UI screenshots, or conceptual artwork when asked for mockups or previews. Only use clean, minimal 2D vector icons, actual programmatic screenshots, or real UI widgets. Place visual mockup files directly on the desktop (`~/Desktop/`).

## Project-Specific Rules & Past Decisions

- **Restart Background Watcher Service on Any Updates**: Whenever Kaffeine DVR is updated in any way — whether editing source code, modifying the systemd service unit, installing/updating from source or pip, or compiling/running an AppImage — always check and restart the background user service (`systemctl --user restart kaffeine-dvr-watcher.service`) so that the running daemon process never runs stale code or outdated database/service logic.
- **Sanitize Recording Titles**: Sanitize all program and recording titles to remove or replace illegal Samba/SMB characters (`/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`) before saving files to disk to prevent remote share mangling.
- **TV Guide Session & Timezone Sync**: Implement resilient session retry logic for TV Passport / EPG fetches and prevent caching failed timezone sync attempts.
- **Database Concurrency**: Guard SQLite database transactions (`kaffeine_dvr.db`, `guide_cache.sqlite`) against concurrency locks between the GUI and background watcher.

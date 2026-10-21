# Release Notes

## v0.9.2

- **Nord & Tokyo Night Built-In Themes**: Expanded both Application Shell Themes and Guide Grid Presets to 10 built-in options with the addition of **Nord** (Arctic slate with frost teal accents and polar night past shading) and **Tokyo Night** (modern midnight navy with electric blue/magenta accents and deep past broadcast shading).
- **Balanced 5x2 Alphabetical Layout**: Both Application Themes and Guide Grid Themes now sort alphabetically by display name, creating an evenly balanced 5 rows × 2 columns layout.
- **Expanded Custom Themes (Up to 8 Presets)**: Increased custom grid theme storage capacity from 6 to 8 saved presets, arranging custom user themes into an even 4 rows × 2 columns grid.
- **Responsive Cursor Feedback**: Enhanced theme switching with a native system wait/busy cursor during stylesheet generation and repainting.
- **Collapsible Caught Shows Drawer in Auto-Record Rules**: Added an interactive collapsible detail drawer to the Auto-Record Rules tab dynamically displaying upcoming broadcasts in the cached guide matched by each rule. The drawer includes show/episode title, channel, air date/time, duration, applied end buffer (with sports detection), and live DVR queue status (Queued, Armed, Recording, Not Queued). Double-clicking any show opens its program details and scheduling options dialog.
- **Auto-Record Rules Match Counter & Header Migration**: Added a dedicated "Matches" column to the Auto-Record Rules table showing the upcoming match count for each rule (e.g. "2 upcoming"). Integrated automatic header state version migration so existing user configurations update seamlessly without column clipping.
- **Splitter Handle Locking on Collapse**: When the caught shows drawer is collapsed, the vertical splitter handle is locked and the container height is constrained to the header bar, preventing the drawer from creating empty gaps or getting misaligned when grabbed.
- **Automatic Scheduled Recording Cancellation on Rule Removal**: Removing an auto-recording rule automatically cancels any upcoming scheduled recordings (in QUEUED or ARMED status) created for that rule from both the SQLite recording queue and Kaffeine scheduler, while preserving any broadcasts still needed by other active rules.
- **Buffer Stepper Controls & Form Layout Polish**: Enhanced buffer configuration across all dialogs (Add Rule, Edit Rule, Manual Record, Adjust Buffer) with tactile NumberStepper controls (`[-] [ value ] [+]`) for reliable adjustment without numeric scroll jumpiness, and cleaned up form checkbox labels to prevent text clipping.
- **Unified Queue Management**: Standardized queue manager instance sharing between the main window and rules engine, ensuring consistent database operations and immediate view synchronization across the application.

## v0.9.1

- **Dedicated Custom Grid Theme Trash Buttons**: Added a direct trash button next to each custom preset in Settings > Themes, allowing custom themes to be deleted without having to activate or switch to them first. Preserves the currently active theme when deleting an inactive custom preset, and removes the obsolete delete icon from the theme editor header.
- **Min Free Space Retention Cleanup & Entry Purging**: Fixed storage auto-cleanup threshold evaluation so low disk space triggers older unprotected recording cleanup reliably. Background daemon now detects disk config changes dynamically via configuration mtime tracking. When files are purged, matching records are now automatically cleared from both the recording schedule queue and history database tables, and database history is kept strictly within maximum entry limits.
- **Sortable Columns Across Recording Schedule**: Enabled interactive column header sorting across all Recording Schedule views (Active Schedule, All Scheduled, and History), making it easy to sort scheduled jobs and completed entries by channel, title, date, duration, or status.
- **Series Rule Recording Protection**: Added full recording protection support to automated series rules, ensuring automated episode recordings inherit retention protection against auto-cleanup.
- **Completed Recording Retention**: Retains completed recordings in the Active Schedule table for up to 6 hours after completion, providing quick visual confirmation before archiving.
- **Scheduler & Conflict Dialog Hardening**: Prevented premature mid-broadcast recovery scans on future scheduled or armed recordings, resolved an issue where clicking conflict option description labels caused an error in the conflict dialog, and ensured guide program details refresh cleanly upon recording cancellation.
- **AppImage Build Automation**: Integrated automatic background watcher service restart (`kaffeine-dvr-watcher.service`) directly into the AppImage packaging script to ensure deployed environments seamlessly run updated service logic.

## v0.9.0

- **Guide Auto-Advance Intervals (1, 2, and 3 Hours)**: Added 1, 2, and 3-hour interval options for Guide Auto-Advance on the hour. Re-engineered block-boundary tracking and dynamic viewport range safeguards so the guide stays anchored to the current multi-hour block and reliably advances when a new interval begins.
- **Grid Guide Options Layout & Instant Jump Highlights**: Restored even 1:1:1 column spacing in Grid Guide Options. Removed lingering focus rings from Jump to Now and Prime Time buttons for clean instant click feedback.
- **Settings Auto-Save & Visual Feedback**: Audited and confirmed immediate auto-save and confirmation feedback (`Settings Saved`) across all General settings.
- **Refined Out-of-the-Box Defaults**: Established optimized defaults for new installations: 10-minute lead time, 210s watcher interval, 50 GB free disk space, 2s timeshift buffer, 2-hour auto-advance on the hour, and Warm Amber / Sunset theme.
- **Expanded Custom Themes (Up to 6 Presets)**: Increased custom grid theme preset storage capacity from 3 to 6 saved presets with an intuitive 2-column compact layout.
- **Centered Custom Anchor Pill**: Permanently centered the `Custom (save up to 6)` anchor pill across the custom grid section regardless of saved preset count.
- **Full 4x2 Grid Theme Parity**: Completed the 8th slot in both Guide Grid Themes and Application Themes with cross-populated matching presets: added **Deep Charcoal** (`#6366f1` indigo accent, slate graphite dark background `#16181d`) to Guide Grid Themes and **Emerald Forest** (`#10b981` pine/emerald green accent, rich deep pine backgrounds `#111a14`) to Application Themes.
- **Web Companion Remote & Tailscale Documentation**: Added dedicated Quickstart guidance for remote zero-config setup using Tailscale alongside live stream support documentation in the in-app Web Access panel.
- **Codebase Optimization & Lint Hardening**: Removed dead variables, cleaned and organized import blocks, eliminated unreferenced symbols, and ensured 100% test suite pass rate.

## v0.8.15

- **Multi-Channel Recording Conflict Resolution**: Added scheduling conflict detection and interactive resolution dialog (`RecordingConflictDialog`) when scheduling recordings that overlap across different channels on tuner-constrained systems. Automatically calculates trimming options to stop the preceding show early or delay the upcoming show, or cancel the request.
- **Left-Aligned Guide Grid Time Headers**: Pinned horizontal TV guide grid time column headers to the left of each section with 10px padding matching the program card indentation below it.
- **Customizable Keyboard Shortcuts & Navigation**: Added full keyboard shortcut customization under Settings > Keyboard Shortcuts with individual editable fields for Guide Navigation Keys (Up, Down, Left, Right), program action hotkeys, view toggles, and global shortcuts.
- **Dedicated Guide Grid & List Keyboard Navigation**: Arrow keys strictly navigate guide grid tiles and list rows, updating tile highlight, program details, and scrolling without triggering accidental playback or popups. Pressing Down initializes keyboard access to the guide when nothing is selected.
- **Remote Web Access Security & Subnet Firewall Rules**: Updated firewall guidance in Remote Web Access settings and the Help guide with explicit instructions for trusted local subnets (e.g. `192.168.1.0/24`) without exposing public ports, highlighting zero-configuration remote access via Tailscale.
- **Antenna Aiming Window Stability & Restoration**: Resolved issue where clicking "Done Aiming" halted playback by unmapping the Kaffeine window. Playback now terminates via D-Bus while keeping Kaffeine open and visible. Swapping channels to aim unminimizes, maps, positions, and raises Kaffeine without audio-only hidden states.
- **X11 Geometry & Repaint Settling**: Added geometry change caching before issuing resize/move operations, bypassing redundant configure requests when Kaffeine is already correctly sized and positioned. Added settling delays and C++ window/menubar repaints to eliminate layout jitter and black unpainted artifacts.
- **Remote Web Access Quick Access URLs**: Added convenient, clickable Quick Access URLs under Settings > Remote Web Access displaying localhost, local LAN IPv4 address, and Tailscale mesh IP for remote devices.
- **Web Companion Security & Password Enforcement**: Made passwords mandatory before enabling the Web Companion server. Added an inline Reset button to clear password protection and disable the server in one click.
- **Rate Limiting & 15-Minute Lockout**: Implemented anti-brute-force protection tracking failed login attempts per client IP. Limits incorrect passwords to 5 attempts before enforcing a 15-minute temporary lockout.
- **Minimized Playback & Clean Audio Termination**: Prevented Kaffeine from playing audio when launched minimized and ensured playback is immediately terminated on session end.
- **Silent Channel Signal Scanning**: Switched background channel scanning to silent D-Bus tuning, eliminating window unminimizing and screen flickering during signal scans.
- **Interface Streamlining**: Simplified main navigation tab title from "Web TV Guide Browser" to "TV Guide".

## v0.8.14

- **Active Recording Conflict Protection**: Added protection to prevent active scheduled recordings from being stopped or deleted when attempting to watch another channel from the Guide. Prompts with a confirmation dialog before switching channels, and directly plays active recordings on the same channel without prompt or interruption.
- **Multi-Tuner Hardware Auto-Detection & Capacity Guard**: Automatically detects physical DVB/ATSC frontend tuners under `/dev/dvb` with configurable manual override in Settings > General. Systems with 2 or more tuners allow simultaneous live TV viewing and background recording across different channels without prompt or interruption, only prompting when all available hardware tuners are occupied.
- **Zero-Byte Dead Stream Watchdog & Fast Tuner Release**: Added automated stream monitoring in the background Watcher daemon that detects stalled or dead broadcast streams (0 bytes written after configurable timeout, default 8s down to 3s). Automatically cancels dead recordings in Kaffeine via D-Bus, cleans up 0-byte orphan files, and immediately releases the hardware tuner.
- **Signal Health Status Dots in Guide Grid**: Added real-time visual signal health indicator dots directly under channel names in the Guide Grid vertical headers (Yellow for weak carrier/no lock, Red for no carrier/no signal) with interactive status hover tooltips and bi-directional channel alias matching.
- **Cross-Distribution SSL/TLS Certificate Auto-Resolution**: Fixed `[SSL: CERTIFICATE_VERIFY_FAILED]` errors on Debian, Ubuntu, Kubuntu, Linux Mint, and HTPC systems when running the standalone AppImage. Automatically detects host system CA certificate bundles across all Linux distributions (`/etc/ssl/certs/ca-certificates.crt`, `/etc/pki/tls/certs`, etc.) and includes a bundled fallback certificate authority inside the AppImage.
- **Case-Insensitive Channel & Network Resolution**: Intelligent normalization and alias mapping (`ConfigManager.resolve_channel`) between guide network keys (e.g. `SUNS`) and Kaffeine database channel names (e.g. `Suns`), ensuring D-Bus scheduling and multi-tuner streaming lock accurately without case mismatch errors.
- **Accurate Playback File Matching**: Refined storage manager active file lookup to avoid false-positive fuzzy matches on common stop words across concurrent recordings, ensuring live timeshifting strictly launches the correct channel stream.
- **Guide Context Menu Crash Fix**: Resolved an `AttributeError` when opening the guide context menu during an active timeshift session.
- **Documentation & Walkthrough Clarifications**: Expanded README and in-app Quick Setup walkthrough with initial 1:1 raw hardware tuner import mappings vs. cleaned GUI display names and TV Passport affiliate configuration.


## v0.8.13

- **AppImage Standalone Runtime Fix**: Resolved `ImportError: attempted relative import with no known parent package` when launching packaged standalone AppImage bundles by moving web server and scanner imports to the top-level package namespace with robust fallback handlers.
- **EPG Web Companion Enhancements**: Redesigned the companion web guide into an anchored two-panel layout keeping channel columns permanently fixed on the left while panning horizontally, made row heights compact, added channel filtering dropdown to the toolbar, and preserved grab-to-pan touch and mouse navigation.

## v0.8.12

- **Remote Web Companion & Downloadable Recordings**: Introduced the lightweight, dependency-free remote web companion with 24-hour EPG Grid and List views, past show trimming, grab-to-pan scrolling, channel filtering, and named file downloads.
- **Weak or No Signal Detection & Auto Tuner Release**: Implemented real-time stream data monitoring at channel start with configurable buffer timeout. Automatically cancels the recording in Kaffeine via D-Bus, cleans up 0-byte partial files, frees the hardware tuner, and displays an informative warning popup if no signal is received.
- **EPG Grid View Enhancements**: Redesigned the web companion EPG Grid into a 2-column layout with permanently anchored channel column on the left, compact 44px rows, semi-transparent 30% opacity timeline marker, and grab-to-pan scrolling.
- **Theme Color Distinctiveness**: Assigned signature representative accent colors to all built-in guide grid theme preset chips (Cyberpunk, Emerald Forest, Midnight Navy, Nordic Frost, OLED High Contrast, Retro Synthwave, Warm Amber) for maximum visual clarity.
- **Factory Default Settings Refinement**: Updated default preferences to 40-minute sports auto-extend buffer, 180-second watcher polling interval, 2-minute notification lead time, and 2-second timeshift initial buffer.
- **Performance & Storage Optimizations**: Precompiled regex matching patterns in `StorageManager` to speed up directory searches and active stream detection.

## v0.8.11

- **Idle CPU Optimization**: Eliminated redundant 1-second stylesheet parsing and canvas invalidation on the top-corner clock, bringing idle CPU consumption down to flat 0.00%.
- **Grid Options Box Checkbox Alignment**: Repositioned the "Disable" checkboxes in Sub-Column 2 immediately adjacent to their items (Live Badge, Live Tile Tint, Time Line, Clock), and moved the Auto-Advance HelpBadge to the right of its checkbox.
- **Guide Sync & Channel Import UI Reorganization**: Relocated the Guide Sync progress bar and real-time status text to Settings > Guide Sources and Health directly next to the "Sync Guide Now" button. Moved channel import and reset buttons above the channel mapping box.
- **Resource Lifecycle & Memory Hardening**: Connected `deleteLater` to all background QThread workers on task completion and added explicit post-sync garbage collection.
- **Codebase Organization & Documentation**: Cleaned, sorted, and formatted imports according to PEP 8 standards, eliminated dead code and unused symbols, and added PEP 257 docstrings across all modules.

## v0.8.10

- **Channel Importing & Renaming Setup**: Clarified the channel lineup and renaming section in Settings to focus on guide display names (`Guide Name = Tuned Channel`), using `Fox = KSAZ-HD` as an example, with guidance on Welcome Wizard imports and re-importing.
- **TV Passport Station ID Instructions**: Streamlined station setup instructions using `Guide Name = Station ID` (e.g. `NBC = 1812`, `Fox = 1809`, or `PBS = 1184`), eliminating unnecessary technical jargon.
- **Help and Information Tab Synchronization**: Synchronized the Quick Setup Walkthrough in the Help tab with the updated channel importing, renaming, and TV Passport setup formats.

## v0.8.9

- **Guide Auto-Advance Controls**: Added a customizable minute-past-the-hour stepper and enable/disable toggle for guide auto-advance, with an inline help badge explaining next-hour advancement.
- **Three-Way Guide Unhighlighting**: Added toggle-on-click, click-empty-space to deselect, and Escape key clearing across both EPG Grid and List views.
- **Corner Clock Display & Sizing**: Added a live top-right tab bar clock widget with color customization, show/hide toggle, and a dedicated font size stepper in Settings.
- **Settings UI Polish**: Standardized numeric stepper widths to 130 px, changed Live Badge toggle text to "Disable" for consistency, and aligned auto-advance minute calculations across live sync and manual Jump-to-Now actions.

## v0.8.8

- **Grid Options Three-Column Layout**: Reorganized the Grid Guide Options settings card into three balanced columns for cleaner visual hierarchy.
- **Frameless Embedded Steppers**: Modernized numeric stepper controls with a sleek inset container and borderless inline increment/decrement buttons.
- **Setting Label Streamlining**: Refined setting labels to "Grid Rows" and "Grid Box" for concise, uncluttered presentation.
- **Updated Documentation & Previews**: Refreshed README preview screenshots showcasing the three-line EPG grid views and updated settings panel.

## v0.8.7

- **Three-Line Grid Program Tiles**: Redesigned EPG grid program tiles into three dedicated lines for Primary Show Title, Broadcast Time Range, and Episode Title/Subtitle for superior clarity and reduced truncation.
- **Grid Tile Margins & Badge Clearance**: Refined vertical padding to 5 px and inter-line spacing to 2 px, guaranteeing clean clearance for the lower-right LIVE pill badge and top-right recording dot indicator.
- **Grid Row Height Legibility Floor**: Enforced a 58 px minimum row height baseline in grid zoom calculations so program tiles never collapse below readable multi-line bounds during window resizing.
- **Description Box Height Configuration**: Added user-selectable 2-line or 3-line description box height preference in Settings.

## v0.8.6

- **Past Recording History Indicators**: Added past recording cross-referencing so programs completed in history show a distinct badge and completion tooltip in both Grid and List guide views.
- **Guide Toolbar Refresh Button**: Added a dedicated quick-refresh button next to Prime Time to instantly reload guide listings and active recording statuses.
- **Refined Time Jump Alignment**: Aligned grid view hour-slot jumps with the current hour mark until 50 minutes past the hour.
- **Grid Guide Live Tile Tint Controls**: Renamed the background tint toggle to "Disable" for clear, intuitive toggle state semantics.
- **Settings Layout Optimization**: Repositioned the broadcast category color swatches and secondary guide option controls into adjacent columns, removing excessive whitespace separation.
- **Desktop & Dock Clapperboard Icon Refinement**: Bundled multi-resolution icon assets across XDG and Breeze icon specifications for consistent panel dock, titlebar, and launcher presentation.

## v0.8.5

- **Recording Cancellation & Duplicate Prevention**: Fixed duplicate concurrent recording timers in Kaffeine by introducing active timer pre-checking and thorough multi-target cancellation across D-Bus and SQLite when recordings are stopped or restarted.
- **Default Update Frequency**: Set the default automatic update check interval to weekly.
- **TVPassport Direct Lineup URL**: Updated all TVPassport links in the guide and lineup dialogs to direct to `https://www.tvpassport.com/index.php/lineups` for immediate postal/zip code entry.
- **EPG Grid Recording & Scheduled Indicators**: Differentiated active recording (`● REC` with solid red dot and red border) from scheduled recordings (`○ SCHED` with subtle outline only).
- **EPG List View Enhancements**: Added subtle grid lines (`#2b3242`), removed row index headers, and differentiated scheduled vs active recordings.
- **Release Notes Modal Viewer**: Added an interactive "View Release Notes..." modal dialog with formatted changelog viewer in Settings -> Updates tab and status bar.
- **AppImage Checkmark Rendering**: Bundled checkmark assets and fixed indicator icon resolution in read-only SquashFS AppImage environments.

## v0.8.4

- **List View Navigation & Performance**: Fixed initial auto-scroll so list view immediately jumps to the first live or upcoming program on its first activation, matching subsequent switches.
- **Direct DBus Channel Tuning**: Implemented direct KDBusService CommandLine parameter passing to tune live TV channels cleanly without requiring synthetic keypresses.
- **Recording Indicator Redesign**: Replaced large rectangular badges with clean red dot indicators on EPG grid tiles for a more polished look.
- **Sports Auto-Extend UI**: Aligned the sports buffer duration spinbox with the rest of the form input fields and repositioned the auto-extend toggle to the right.
- **AppImage Distribution & Metadata**: Built and released a standalone x86_64 AppImage with embedded Python and PyQt6 runtimes, complete desktop metadata, and AppManager package compatibility.
- **Background Watcher CLI Dispatching**: Fixed argument dispatch in entrypoint so CLI daemon modes like `--watch` execute headlessly as background services rather than opening a second GUI window.
- **Background Service Auto-Provisioning**: Automated systemd user unit provisioning directly from the AppImage/application with dynamic `ExecStart` path resolution, allowing the background watcher service to enable, start, and run seamlessly without requiring manual install scripts.
- **Documentation & UI Previews**: Refreshed README installation workflows (clarifying standalone AppImage vs. source installation), overview sections, and preview screenshots.

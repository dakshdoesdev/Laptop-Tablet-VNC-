# Dual-Tablet VNC Design Report

Date: 2026-03-21

## Scope

Research and design direction for a low-latency Hyprland + wayvnc tablet-display manager with:
- one ADB-capable tablet
- one manual host/IP tablet
- a desktop-first graphical control panel

## NotebookLM Findings

Notebook used:
- https://notebooklm.google.com/notebook/ced1547f-c4ee-4afe-a280-f7c0cdd34282

NotebookLM output converged on the same core architecture as the local script audit:

1. Use named per-tablet profiles instead of one shared profile.
- `usb` for the ADB-capable tablet
- `typec` for the manual host/IP tablet

2. Keep the current display pipeline.
- create the virtual monitor with `hyprctl output create headless`
- expose the chosen output with `wayvnc`

3. Store per-tablet settings independently.
- connection mode
- host/IP
- port
- resolution
- refresh
- max FPS
- output position
- workspace mapping
- alignment

4. Keep the CLI as a power-user fallback, but make GUI the primary path.

NotebookLM-recommended baseline defaults:
- resolution: `1280x800`
- output refresh: `60 Hz`
- max FPS: `30`

NotebookLM-highlighted failure states:
- missing ADB device
- missing manual IP/host
- occupied port
- invalid timing pair such as `60 FPS` capture over `30 Hz` output
- bad tether fallback behavior

## Stitch Findings

Stitch authentication worked with the Google session reused from the exported browser auth state.

Confirmed live behavior:
- Stitch landing page loads successfully
- authenticated workspace is reachable
- projects list is visible
- prompt editor exists as a TipTap `role="textbox"`
- `Generate designs` becomes enabled when prompt text is entered through real typing

Artifacts:
- [stitch-home.png](/home/dux/Work/tries/projects/vnc-dual-tablet-research-2026-03-21/artifacts/stitch-home.png)
- [stitch-design-flow.png](/home/dux/Work/tries/projects/vnc-dual-tablet-research-2026-03-21/artifacts/stitch-design-flow.png)
- [stitch-generated.png](/home/dux/Work/tries/projects/vnc-dual-tablet-research-2026-03-21/artifacts/stitch-generated.png)

Observed limitation:
- headless automation could populate the Stitch prompt and enable the generate button
- but the generation flow did not transition into a completed design/project state during automated runs
- so the report below is based on the validated prompt surface, your prompt, and the NotebookLM architecture findings, not a fully captured Stitch-generated screen set

## Recommended GUI

### Main Dashboard

The main dashboard should be the daily-driver surface.

Structure:
- app title: `Tablet VNC`
- two profile cards:
  - `USB Tablet`
  - `Type-C Tablet`
- each card should show:
  - status
  - transport mode
  - host/IP
  - port
  - refresh
  - FPS
  - current output placement
- each card should expose:
  - `Start`
  - `Stop`
  - `Edit`

Global action row:
- `Logs`
- `Doctor`
- `Benchmark`

### Settings View

The secondary settings view should be explicit and mechanical, not decorative.

Fields:
- profile name
- connection mode
- host/IP
- port
- resolution
- refresh
- FPS
- output position
- workspace count
- workspace start
- vertical alignment

Validation rules:
- reject `FPS > refresh`
- require host/IP for manual-host profile
- warn when the requested port is already in use

### Diagnostics Drawer

Show operational truth, not generic help text.

Fields:
- output name
- bind address
- current transport
- current profile
- wayvnc version
- last error or warning

Examples of warnings:
- `ADB device not detected`
- `Manual host is empty`
- `Port 5900 already in use`
- `Profile refresh/FPS mismatch`

## Visual Direction

The right visual direction is a compact Linux control surface, not a consumer settings app.

Recommended look:
- dark graphite base
- muted gray cards
- crisp borders
- orange accents for active/running state
- compact spacing
- strong, technical typography
- minimal ornament

Avoid:
- mobile-style cards with oversized padding
- bright gradients
- soft playful visuals
- generic dashboard chrome

## Product Recommendation

The best product shape is:
- GUI first
- CLI second
- per-tablet configuration ownership
- stable low-latency defaults
- aggressive validation before start

That means the UI is not just a launcher. It is a profile-aware control surface for:
- starting the right tablet path
- preventing invalid timing combos
- exposing runtime state fast
- making recovery obvious when a device or port is missing

## Best Next Build Step

Implement the GUI in this order:

1. Main dashboard with two saved profile cards
2. Settings modal/screen with validation
3. Diagnostics drawer wired to real script output
4. Shared backend config/profile layer
5. Optional benchmark view once the main control flow is stable

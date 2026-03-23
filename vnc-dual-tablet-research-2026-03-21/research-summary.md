# Research Summary

Date: 2026-03-21

## What the current stack is

Local inspection shows:
- Host compositor: Hyprland on Wayland
- Capture server: `wayvnc 0.9.1-1`
- Current wrapper scripts:
  - `/home/dux/.local/bin/tablet-vnc`
  - `/home/dux/.local/bin/tablet-vnc-top`
- Current approach: create a Hyprland headless output, place it next to the laptop panel, and stream that output with `wayvnc`.

## Local script findings

- The current script already prefers a headless output, which matches Hyprland's recommended model for VNC/RDP style use.
- The saved profile currently has a mismatch:
  - `PROFILE_REFRESH=30`
  - `PROFILE_FPS=60`
- That mismatch is a bad default for low-latency daily use because the stream attempts to capture faster than the virtual output refreshes.
- The current tether flow can fall back to `0.0.0.0`. That is noisy for local use and contributed to the recent bind conflict in the log.
- The scripts are duplicated between `tablet-vnc` and `tablet-vnc-top`, which makes future tuning drift likely.
- The current config model is single-profile. That does not fit your new hardware reality:
  - one tablet can use ADB
  - the other tablet needs a non-ADB path

## What the official docs support

From wayvnc docs and local man pages:
- `wayvnc` exposes one output at a time and supports selecting that output explicitly.
- It supports max FPS limiting with `-f`.
- It supports a control socket and runtime interaction via `wayvncctl`.
- It listens on localhost by default.
- Binding to `0.0.0.0` is supported, but the upstream README explicitly warns not to do this on public networks without auth.

From Hyprland docs:
- `hyprctl output create headless <name>` is the intended mechanism for VNC/RDP/Sunshine style fake displays.

## Best practical direction

For your setup, the best direction is not "more flags in one profile". It is:
- named profiles per tablet
- one graphical launcher/settings UI
- one shared backend script
- USB/ADB flow for the ADB-capable tablet
- manual host/IP flow for the non-ADB tablet

## Recommended defaults

Balanced daily default:
- resolution: `1280x800`
- refresh: `60`
- max fps: `30`
- position: configurable
- transport:
  - `usb` profile: ADB-capable flow
  - `typec` profile: manual host/IP flow

Why this default:
- `60 Hz / 30 FPS` is the safer low-latency baseline for an older Android tablet viewer.
- `60 Hz / 60 FPS` can be offered as an "absolute" preset later, but should not be the default without measuring decode smoothness on the client.

## Architecture recommendation

Implement these layers:

1. Shared backend
- one script or sourced library with all start/stop/status logic
- both output variants and both tablets use the same logic

2. Profile storage
- one profile file per tablet
- no more single global `profile.env`

3. Graphical UI
- main entrypoint for daily use
- choose tablet
- choose action
- edit settings
- save per-tablet config

4. CLI compatibility
- keep direct commands for fast terminal use
- examples:
  - `tablet-vnc usb`
  - `tablet-vnc typec`
  - `tablet-vnc gui`

## NotebookLM angle

NotebookLM is useful here for:
- collecting official wayvnc / Hyprland / Google notes in one place
- asking cross-source questions like:
  - "what settings reduce latency without increasing connection jitter?"
  - "what is the cleanest way to support two transport modes in one launcher?"
  - "how should I design a tablet picker UI with minimal friction?"

## Stitch angle

Stitch is a good fit for the UI-only part:
- small settings/launcher utility
- clear modes and device cards
- quick panel-based layout
- exportable frontend concepts

The UI should feel like a control panel, not a generic mobile app.

# Dual Tablet VNC Manager Source Pack

Use this as a NotebookLM source document.

## Problem

I run Hyprland on Arch Linux and use `wayvnc` to create a virtual tablet display through a headless output. The setup now needs to support two different tablets:

- Tablet A: can use ADB / USB workflow
- Tablet B: does not have a usable ADB path and needs a manual host/IP style connection path

The current script is single-profile and assumes one connection path. I need a cleaner architecture and UI for switching between the two tablets while keeping low latency.

## Current host context

- OS: Arch Linux
- WM/compositor: Hyprland
- Display server: Wayland
- Host GPU setup: AMD iGPU + NVIDIA RTX 3050 laptop GPU
- VNC server: `wayvnc 0.9.1`
- Virtual display strategy: `hyprctl output create headless`

## Current implementation shape

- A script creates a headless output such as `TABLET-VNC`
- The script positions the output around the main monitor
- `wayvnc` captures that output and serves it over a chosen IP/port
- Settings are currently stored as one shared profile file

## Current pain points

- One profile cannot represent two different tablets cleanly
- Old saved state can create bad timing combinations such as `30 Hz` output with `60 FPS` capture
- Tether mode can fall back to `0.0.0.0`, which is not ideal for a local-only workflow
- The main and top variants of the script duplicate logic

## What I want

- Two named tablet profiles:
  - `usb`
  - `typec`
- A graphical launcher/settings UI
- Fast switching between tablets
- Good low-latency defaults
- Clear config ownership per tablet
- CLI fallback for quick power use

## Recommended configuration direction

Per-tablet profiles should store:
- profile name
- connection mode
- host/IP
- port
- resolution
- refresh
- max fps
- output position
- workspace mapping
- alignment

## Low-latency defaults

Start with:
- resolution: `1280x800`
- refresh: `60`
- max fps: `30`

Only expose `60 FPS` as an optional higher-load preset after verifying the Android client handles it smoothly.

## Questions to explore

- What is the cleanest per-tablet config schema for this setup?
- What UX is best for switching between an ADB-capable and non-ADB tablet?
- What should the graphical launcher show on one screen vs a secondary settings screen?
- What wayvnc settings matter most for perceived latency in a local USB-tether or direct local network workflow?
- How should errors be surfaced for missing ADB devices, missing manual IPs, or occupied ports?

## Seed sources

- wayvnc official repo and docs
- Hyprland docs for `hyprctl output create headless`
- NotebookLM docs for notebook creation and source discovery
- Google Stitch product references

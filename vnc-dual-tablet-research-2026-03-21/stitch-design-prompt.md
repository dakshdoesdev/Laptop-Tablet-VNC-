# Stitch Prompt

Design a compact desktop control panel for a Linux tool called "Tablet VNC".

The app is used on a dark minimal Arch Linux + Hyprland setup. It manages virtual tablet displays created through a headless output and streamed with VNC. The user has two tablets and wants to switch between them fast.

Product goals:
- ultra-fast switching between two tablet profiles
- low-friction daily use
- settings are clear but not cluttered
- feels technical, sharp, and intentional
- not generic mobile UI

Primary users:
- power users on Linux
- keyboard-heavy workflow
- dark minimal desktop setups

Core screens:

1. Main launcher
- title: Tablet VNC
- two large profile cards:
  - USB Tablet
  - Type-C Tablet
- each card shows:
  - connection mode
  - host/IP
  - port
  - refresh
  - fps
  - current status
- primary actions on each card:
  - Start
  - Stop
  - Edit
- one compact global action row:
  - Open logs
  - Doctor
  - Quick benchmark

2. Settings screen
- profile name
- connection mode selector
- host/IP field
- port field
- resolution dropdown
- refresh dropdown
- fps dropdown
- output position selector
- workspace count
- workspace start
- vertical alignment selector
- save and cancel actions

3. Diagnostics drawer
- current output name
- current bind address
- current transport mode
- current wayvnc version
- simple warnings and suggestions

Visual direction:
- dark graphite background, not pure black
- orange accents for active/connected state
- muted gray panels with crisp borders
- strong typography, compact spacing
- slight terminal/control-room feel
- clean cards, subtle depth, no playful gradients

Interaction direction:
- status should be readable at a glance
- the currently active tablet should feel locked in and obvious
- disabled or invalid states should be very clear
- settings should feel like a power tool, not a consumer app

Output requested:
- desktop-first UI
- a polished launcher/control panel
- one main dashboard plus one settings view
- consistent dark Linux aesthetic

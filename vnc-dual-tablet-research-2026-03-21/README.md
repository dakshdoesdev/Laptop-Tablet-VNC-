# Dual-Tablet VNC Research Pack

Generated: 2026-03-21

This folder packages the research and design inputs for your Hyprland + wayvnc dual-tablet setup.

Files:
- `research-summary.md`: concise technical findings, local context, and recommended direction
- `notebooklm-source-pack.md`: a clean source document you can upload into NotebookLM
- `notebooklm-discover-prompt.txt`: prompt to use with NotebookLM "Discover sources"
- `stitch-design-prompt.md`: prompt for Google Stitch to generate the graphical tablet launcher/settings UI

Current blockers from this session:
- NotebookLM auth helper failed twice on 2026-03-21, so no notebook was created from here.
- `npx playwright --version` timed out after 10s on 2026-03-21, so browser automation was not available in this shell.

Best next action on your side:
1. Open NotebookLM in a normal browser and log in.
2. Create a new notebook called `Dual Tablet VNC Manager`.
3. Add `notebooklm-source-pack.md` as a source.
4. Optionally use `notebooklm-discover-prompt.txt` with Discover Sources.
5. Open Stitch and paste `stitch-design-prompt.md`.

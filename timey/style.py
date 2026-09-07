"""Timey's grayscale look.

The whole stylesheet is monochrome: instead of relying on the accent
color (which is not even configurable on every system), the palette is
rendered from one of two hand-picked neutral scales. Only neutral gray
tokens appear anywhere in the UI — no hue, by design.
"""

from __future__ import annotations

#: Grayscale palettes keyed by theme name. Neutral-only by design.
PALETTES: dict[str, dict[str, str]] = {
    "dark": {
        "main": "#f0f0f0",          # primary text / filled control
        "onmain": "#101010",        # text drawn on top of `main`
        "main_hover": "#ffffff",
        "main_active": "#c9c9c9",
        "muted": "#8b8b93",         # secondary text
        "panel": "#191919",         # cards / panels
        "panel_hover": "#2a2a2a",
        "border": "#303030",
    },
    "light": {
        "main": "#1b1b1b",
        "onmain": "#ffffff",
        "main_hover": "#000000",
        "main_active": "#3a3a3a",
        "muted": "#6e6e74",
        "panel": "#ffffff",
        "panel_hover": "#e9e9e9",
        "border": "#e0e0e0",
    },
}

_CSS_TEMPLATE = """
/* ── Timey — grayscale theme ───────────────────────────────
   Neutral color tokens (written as @name@) are injected at
   runtime by style.build_css(). No hues anywhere, by design. */

.timey-state {
  font-size: 12px;
  font-weight: 700;
  color: @@muted@@;
}
.timey-state.running,
.timey-state.paused {
  color: @@main@@;
}

.timey-main {
  font-family: monospace;
  font-size: 54px;
  font-weight: 300;
  color: @@main@@;
}

.timey-hint {
  font-size: 12px;
  color: @@muted@@;
}

/* ── buttons ─────────────────────────────────────────────── */
button.timey-btn {
  border-radius: 999px;
  padding: 9px 26px;
  font-weight: 600;
  border: 1px solid transparent;
  background-image: none;
}
button.timey-btn:disabled {
  opacity: 0.35;
}

button.timey-primary {
  background-color: @@main@@;
  color: @@onmain@@;
}
button.timey-primary:hover {
  background-color: @@main_hover@@;
}
button.timey-primary:active {
  background-color: @@main_active@@;
}

button.timey-ghost {
  background-color: @@panel@@;
  border-color: @@border@@;
  color: @@main@@;
}
button.timey-ghost:hover {
  background-color: @@panel_hover@@;
}
button.timey-ghost:disabled {
  color: @@muted@@;
}

button.timey-start {
  min-width: 140px;
}

/* ── lap panel ───────────────────────────────────────────── */
.timey-scroller {
  background: transparent;
}

.timey-lapwrap {
  background-color: @@panel@@;
  border: 1px solid @@border@@;
  border-radius: 16px;
}

.timey-laps {
  background-color: transparent;
}

.timey-laprow {
  background-color: transparent;
  border-radius: 12px;
  margin: 3px 6px;
}
.timey-laprow:hover {
  background-color: @@panel_hover@@;
}

.timey-laprow .timey-lapid {
  font-size: 12px;
  font-weight: 700;
  color: @@muted@@;
}
.timey-laprow .timey-laptotal {
  font-family: monospace;
  font-size: 16px;
  font-weight: 600;
  color: @@main@@;
}
.timey-laprow .timey-lapsplit {
  font-family: monospace;
  font-size: 11px;
  color: @@muted@@;
}

.timey-empty {
  color: @@muted@@;
  font-size: 13px;
}

/* ── countdown cards ────────────────────────────────── */
.timey-card {
  background-color: @@panel@@;
  border: 1px solid @@border@@;
  border-radius: 16px;
  padding: 14px 18px;
}

.timey-tname {
  font-weight: 700;
  color: @@main@@;
}
.timey-tstatus {
  font-size: 11px;
  font-weight: 700;
  color: @@muted@@;
}
.timey-tstatus.running,
.timey-tstatus.finished {
  color: @@main@@;
}

.timey-ttotal {
  font-family: monospace;
  font-size: 12px;
  color: @@muted@@;
}

.timey-tleft {
  font-family: monospace;
  font-size: 42px;
  font-weight: 300;
  color: @@main@@;
}

/* ── alarm cards ───────────────────────────────── */
.timey-alarmtime {
  font-family: monospace;
  font-size: 30px;
  font-weight: 700;
  color: @@main@@;
}
.timey-alarmmeta {
  font-size: 12px;
  color: @@muted@@;
}

button.timey-daybtn {
  background-image: none;
  background-color: transparent;
  border: 1px solid @@border@@;
  border-radius: 999px;
  padding: 4px 11px;
  font-size: 12px;
  font-weight: 600;
  color: @@muted@@;
}
button.timey-daybtn:hover {
  color: @@main@@;
}
button.timey-daybtn:checked {
  background-color: @@main@@;
  border-color: @@main@@;
  color: @@onmain@@;
}

/* ── world clock cards ─────────────────────────── */
.timey-worldname {
  font-weight: 700;
  color: @@main@@;
}
.timey-worldmeta {
  font-size: 12px;
  color: @@muted@@;
}
.timey-worldtime {
  font-family: monospace;
  font-size: 30px;
  font-weight: 300;
  color: @@main@@;
}

.timey-card progressbar trough {
  background-color: @@border@@;
  border-radius: 999px;
  min-height: 8px;
}
.timey-card progressbar progress {
  background-color: @@main@@;
  border-radius: 999px;
  min-height: 8px;
}

button.timey-sm {
  padding: 6px 16px;
}

button.timey-primary label,
button.timey-ghost label {
  color: inherit;
}

button.timey-iconbtn {
  background-color: transparent;
  color: @@muted@@;
  border-radius: 999px;
  padding: 4px;
  background-image: none;
}
button.timey-iconbtn:hover {
  background-color: @@panel_hover@@;
  color: @@main@@;
}

/* ── grayscale chrome (header switch, dialogs) ─────── */
.timey-switch {
  border: 1px solid @@border@@;
  border-radius: 999px;
  padding: 3px;
}

button.timey-switchbtn {
  background-image: none;
  background-color: transparent;
  border: none;
  border-radius: 999px;
  padding: 4px 16px;
  font-weight: 600;
  color: @@muted@@;
}
button.timey-switchbtn label {
  color: inherit;
}
button.timey-switchbtn:hover {
  color: @@main@@;
}
button.timey-switchbtn:checked {
  background-color: @@main@@;
  color: @@onmain@@;
}

button.suggested-action {
  background-color: @@main@@;
  color: @@onmain@@;
}
button.suggested-action:hover {
  background-color: @@main_hover@@;
}
button.suggested-action:active {
  background-color: @@main_active@@;
}
"""


def build_css(theme: str = "dark") -> str:
    """Render the full grayscale stylesheet for the requested theme."""
    palette = PALETTES.get(theme) or PALETTES["dark"]
    css = _CSS_TEMPLATE
    for key, value in palette.items():
        css = css.replace(f"@@{key}@@", value)
    return css

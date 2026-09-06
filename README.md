# Timey ⏱

A deliberately **grayscale** stopwatch for the Linux desktop — built with
Python, GTK 4 and Libadwaita. Dark mode by default, with a one-click
toggle for light mode.

<p align="center"><em>Monochrome by design. No hue, no accent, no fuss.</em></p>

## Features

- Monotonic-clock stopwatch with centisecond precision (`HH:MM:SS.cc`)
- Lap recording (per-lap splits + cumulative times)
- **Grayscale styling** in both color schemes — the palette is injected at
  runtime, so the app stays neutral even where accent colors aren't supported
- **Dark mode by default** with a persistent dark ⇄ light toggle
- Keyboard shortcuts: `Space` start/pause · `L` lap · `R` reset
- Preferences persisted to `~/.config/timey/config.ini` (no GSettings
  schema needed to run from a checkout)

## Requirements

Timey needs Python 3 with GObject introspection bindings plus GTK 4 and
Libadwaita. On Arch-based systems (including Omarchy):

```bash
sudo pacman -S python-gobject gtk4 libadwaita
```

> Runtime system packages only — Timey itself has **zero** pip dependencies.

## Run it

From a checkout of the repository:

```bash
python3 -m timey
```

Or install it as a command (entry point `timey`):

```bash
pip install -e .
timey
```

Run the engine unit tests with:

```bash
python3 -m unittest discover -s tests
```

## Desktop integration (optional)

To get a launcher entry in your app grid:

```bash
install -Dm644 packaging/io.github.pixlpixlpixl.Timey.svg \
  ~/.local/share/icons/hicolor/scalable/apps/io.github.pixlpixlpixl.Timey.svg
install -Dm644 packaging/timey.desktop ~/.local/share/applications/
update-desktop-database ~/.local/share/applications 2>/dev/null || true
```

## Keys & shortcuts

| Key     | Action        |
| ------- | ------------- |
| `Space` | Start / pause / resume |
| `L`     | Record a lap  |
| `R`     | Reset         |

The theme toggle (sun/moon) lives in the header bar. Your choice is saved
and remembered on the next launch.

## Environment & secrets

Local overrides and (future) secrets live in a `.env` file which is
**gitignored** — it can never be committed:

- Copy `.env.example` → `.env` and fill in your own values.
- Supported keys today: `TIMEY_THEME=dark|light` (first-launch theme).
- `.env` is searched in the current working directory and in
  `~/.config/timey/.env`. Values already present in your shell
  environment always win.

## Repository hygiene

This repository is meant to be made public eventually. Guardrails included:

- `.gitignore` ignores `.env`, `.env.*` (except the example), keys,
  caches, build artifacts and editor droppings.
- Before ever pushing secrets or making the repo public, double-check with:

  ```bash
  git ls-files | grep -iE '\.env|secret|key|token|credential' || true
  git status --ignored --short | grep '^!!' | grep -E '\.env' || true
  ```

## Project layout

```
timey/
  app.py        GTK 4 / Libadwaita application & window
  stopwatch.py  pure-Python timing engine (unit-tested)
  style.py      grayscale stylesheet generator
  prefs.py      persisted preferences (INI)
  env.py        tiny .env loader
tests/          engine unit tests
packaging/      desktop entry + app icon
```

## License

[MIT](LICENSE)

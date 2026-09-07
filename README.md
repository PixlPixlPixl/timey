# Timey

A deliberately **grayscale** stopwatch **and multi-countdown timer** for the
Linux desktop — built with Python, GTK 4 and Libadwaita. Dark mode by
default, with a one-click toggle for light mode.

<p align="center"><em>Monochrome by design. No hue, no accent, no fuss.</em></p>

## Features

- **Stopwatch** — monotonic-clock timing with centisecond precision
  (`HH:MM:SS.cc`) and lap recording (per-lap splits + cumulative times)
- **Countdown timers** — run **any number at once**; each timer can have a
  name, live progress bar, and fires a desktop notification when finished
- **Grayscale styling** in both color schemes — the palette is injected at
  runtime, so the app stays neutral even where accent colors aren't supported
- **Dark mode by default** with a persistent dark/light toggle
- About dialog links straight to the **Github** repository
- Preferences persisted to `~/.config/timey/config.ini` (no GSettings
  schema needed to run from a checkout)

## Requirements

Timey is pure Python on top of your distro's GTK 4 / Libadwaita /
PyGObject packages — it has **zero** pip dependencies. Install those system
packages first:

| Distro          | Install command                                        |
| --------------- | ------------------------------------------------------ |
| Arch / Omarchy  | `sudo pacman -S python-gobject gtk4 libadwaita`        |
| Debian / Ubuntu | `sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1` |
| Fedora          | `sudo dnf install python3-gobject gtk4 libadwaita`     |

`./install.sh` checks for these and prints the right command if they're missing.

## Install from source (recommended)

Find it on GitHub, clone, and install — no root, no `pip`, nothing to compile:

```bash
git clone https://github.com/PixlPixlPixl/Timey.git
cd Timey
./install.sh
```

The installer targets **your user account** (`~/.local`, no `sudo` needed):

- copies the pure-Python `timey` package to `~/.local/lib/timey/`
- puts a `timey` launcher in `~/.local/bin/`
- registers a **Timey** entry in your app grid plus the stopwatch icon
  (`~/.local/share/applications/` and `~/.local/share/icons/`)

Start it with `timey` in a terminal or from your app launcher.

Useful variations:

```bash
PREFIX=$HOME/.local ./install.sh   # pick a different prefix
./install.sh --uninstall           # remove everything it installed
```

## Run from a checkout (development)

With the system packages from [Requirements](#requirements) in place, run
straight from the source tree:

```bash
python3 -m timey
```

Or install it as an editable console command with pip:

```bash
pip install -e .
timey
```

Run the engine unit tests with:

```bash
python3 -m unittest discover -s tests
```

## Keys & shortcuts

Keyboard shortcuts act on the **Stopwatch** page:

| Key     | Action        |
| ------- | ------------- |
| `Space` | Start / pause / resume |
| `L`     | Record a lap  |
| `R`     | Reset         |

On the **Timers** page, use `+ Add Timer` to add as many countdowns as you
want; each card has its own Start/Pause, Reset and delete button.

The theme toggle (sun/moon) lives in the header bar. Your choice is saved
and remembered on the next launch.

## Environment & secrets

Local overrides and (future) secrets live in a `.env` file which is
**gitignored** — it can never be committed:

- Copy `.env.example` to `.env` and fill in your own values.
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
install.sh     user installer (no root/pip; also handles --uninstall)
timey/
  app.py        GTK 4 / Libadwaita application & window
  stopwatch.py  pure-Python stopwatch engine (unit-tested)
  countdown.py  pure-Python countdown engine (unit-tested)
  style.py      grayscale stylesheet generator
  prefs.py      persisted preferences (INI)
  env.py        tiny .env loader
tests/          engine unit tests
packaging/      desktop entry + app icon (used by install.sh)
```

## License

[MIT](LICENSE)

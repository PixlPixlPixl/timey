# Timey

A grayscale clock app for the Linux desktop — built with Python, GTK 4
and Libadwaita. Dark mode by default, with a light-mode toggle.

## Features

- **Alarms** — set as many as you want. Ring once, daily, or on chosen
  weekdays. Desktop notification and sound when they go off.
- **Stopwatch** — start/pause/reset with lap recording.
- **Timers** — run several countdowns at once.
- **World clock** — current time in your timezone (default) and any
  cities you add.
- **Runs in the background** — alarms and timers keep going when the
  window is closed (on by default when installed).
- **Remembers everything** — alarms, timers, stopwatch history and
  settings are restored on the next launch.

## Requirements

Timey needs these system packages (no pip dependencies):

- Arch / Omarchy: `sudo pacman -S python-gobject gtk4 libadwaita`
- Debian / Ubuntu: `sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1`
- Fedora: `sudo dnf install python3-gobject gtk4 libadwaita`

## Install

```bash
git clone https://github.com/PixlPixlPixl/Timey.git
cd Timey
./install.sh
```

This installs Timey for your user only — no root needed. Start it from
your app grid or by running `timey`.

To remove it later: `./install.sh --uninstall`

## Run from a checkout

```bash
python3 -m timey
```

Run the unit tests with:

```bash
python3 -m unittest discover -s tests
```

## License

[MIT](LICENSE)

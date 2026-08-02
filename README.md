# Batch URL Importer — an Atelier Studio plugin

Imports a whole gallery from one link: Pixiv, DeviantArt, ArtStation,
Twitter/X, Reddit, Tumblr, the booru family, manga readers — 150+ sites,
via [gallery-dl](https://github.com/mikf/gallery-dl).

Atelier Studio's built-in **URL Import** stays the tool for a single
video. This is the one for "give me all 240 images in that feed".

## Why this is a separate download

gallery-dl is licensed **GPL-2.0**. Atelier Studio's installer is kept
free of GPL code, so anything GPL ships as a plugin you choose to
install. Installing this pulls `gallery-dl==1.32.9` from PyPI onto your
machine — Atelier never redistributes it.

This plugin's own code links against gallery-dl and is therefore also
**GPL-2.0**.

## Install

Shop → Import → Batch URL Importer → Install. Nothing to configure.

## Signing in to private galleries

Some sites need a login. This plugin borrows the session from a browser
you are **already signed in with** — pick it under "Sign in using
browser".

Atelier Studio never asks for, stores, or transmits a site password.
gallery-dl itself supports raw credentials in a config file; this
plugin deliberately does not expose that.

## Notes

* **Returns a folder, not a file.** One link makes hundreds of files.
  Because of that it cannot be the first step of a pipeline — import
  first, then run a tool over what you got.
* **Uses no GPU.** Downloading is network and disk. An AMD, Intel or
  CPU-only machine runs this exactly as fast as a 5090 box; the website
  sets the speed.
* **Downloads one file at a time, on purpose.** Going wide gets you
  rate-limited, captcha'd, or banned. A slower import beats a locked
  account.
* **Watch your disk.** A busy artist feed can run to tens of GB. Use
  "Max files" to take a sample first.

## Layout

    __init__.py   exposes TOOL, the whole plugin contract
    tool.py       the Atelier tool: params, progress, output folder
    gdl.py        the ONLY module that imports gallery-dl

gallery-dl has no documented Python API (upstream issue #642 is still
open), so every import of it is quarantined in `gdl.py`. When upstream
moves, that is the one file to fix. The version is pinned, and Atelier
ships a conformance test that fails if an upgrade changes the parts
this adapter relies on.

The interesting design notes — why `job.out` and not `hooks`, and how
the progress bar avoids the frozen-0% bug — are in `gdl.py`'s docstring
and in `docs/research-gallery-dl.md` in the main repo.

## License

GPL-2.0-only. See LICENSE.

# Batch URL Importer — an Atelier Studio plugin
# Copyright (C) 2026 Tejeswaar
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
#
# It links against gallery-dl (GPL-2.0) and is therefore GPL-2.0 too.
# Distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.

"""The ONLY module in the app that imports gallery-dl.

gallery-dl has no documented Python API — "document how to use as a
library" is still open upstream, and what works today is internals that
a minor release may move. So every import of it is quarantined here:
when upstream changes, this is the one file to fix.

Two things were verified by probe against 1.32.9 rather than assumed,
because guessing at an undocumented API is how you ship a bug:

  * DataJob enumerates a gallery WITHOUT downloading a byte, so we can
    count items up front and show an honest bar from item one.
  * job.out is the real progress contract (upstream ships three
    implementations of it: NullOutput, PipeOutput, TerminalOutput) and
    it reports BYTES, not just files.

The `hooks` mechanism looked like the obvious choice and is a trap:
DownloadJob.hooks is a plain `()` until postprocessors are configured,
so registering a callback needs a private-attribute hack, and an
exception raised inside a hook is swallowed. `out` needs neither.
"""
import io
import re
from pathlib import Path

VERSION = "1.32.9"          # the version this adapter was written for

# Message.Url — a downloadable item. Numeric because gallery_dl.message
# is itself internal; the value has been 3 for the life of the project.
_MSG_URL = 3


def installed_version() -> str:
    from gallery_dl import version
    return version.__version__


def folder_name(url: str) -> str:
    """A readable, Windows-safe folder name derived from the URL.

    'https://www.pixiv.net/users/12345' -> 'pixiv.net_users_12345'
    """
    # scheme first, THEN trailing slashes — the other order turns a bare
    # "https://" into a folder literally named "https"
    stripped = re.sub(r"^https?://(www\.)?", "", url.strip()).rstrip("/")
    safe = re.sub(r'[<>:"/\\|?*]+', "_", stripped)
    safe = re.sub(r"_{2,}", "_", safe).strip("._ ")
    return (safe[:80] or "import")


def configure(dest: Path, *, limit: int = 0, include_video: bool = True,
              browser_cookies: str = "", ffmpeg_dir: str = "") -> None:
    """Point gallery-dl at our folder and our settings, not the user's.

    gallery-dl normally reads ~/gallery-dl.conf. We load it (a power
    user may have site credentials in there) and then override the
    things that are ours to decide: where files go, and that nothing
    is written to a terminal we do not have.
    """
    from gallery_dl import config

    config.clear()
    config.load()                                   # user's own config, if any
    config.set((), "base-directory", str(dest))
    config.set((), "directory", [])                 # flat: no site subfolders
    config.set(("output",), "mode", "null")         # we are not a terminal
    config.set(("output",), "progress", False)

    # byte-level progress after 1s of a slow file instead of the 3s
    # default — this is what keeps a single large video from looking
    # frozen, the exact failure the yt-dlp importer had to patch around
    config.set(("downloader",), "progress", 1.0)

    if limit > 0:
        config.set(("extractor",), "image-range", f"1-{limit}")

    if include_video:
        config.set(("downloader", "ytdl"), "module", "yt_dlp")
        if ffmpeg_dir:
            config.set(("downloader", "ytdl"), "raw-options",
                       {"ffmpeg_location": ffmpeg_dir})
    else:
        config.set(("extractor",), "videos", False)

    # Sites needing a login use the browser session the user already
    # has. Atelier never asks for, stores, or transmits a site password
    # — gallery-dl supports raw credentials in a config file and we
    # deliberately do not expose that.
    if browser_cookies:
        config.set(("extractor",), "cookies", [browser_cookies])


def count_items(url: str) -> int | None:
    """How many files this URL yields, without downloading any of them.

    Returns None if the gallery could not be enumerated (private, gone,
    or an extractor that will not simulate) — the caller then shows an
    honest indeterminate status instead of a made-up total.
    """
    from gallery_dl import job

    try:
        probe = job.DataJob(url, file=io.StringIO())
        probe.run()
        if probe.exception is not None:
            return None
        return sum(1 for entry in probe.data if entry[0] == _MSG_URL)
    except Exception:
        return None


class Reporter:
    """Receives gallery-dl's progress. Implements the same four methods
    as upstream's own output classes."""

    def start(self, path: str) -> None: ...
    def success(self, path: str) -> None: ...
    def skip(self, path: str) -> None: ...
    def progress(self, bytes_total, bytes_downloaded,
                 bytes_per_second) -> None: ...


def download(url: str, reporter: Reporter) -> int:
    """Run the download. Returns gallery-dl's exit status (0 = success).

    Cancellation is not cooperative here and does not need to be: the
    scheduler kills the whole worker process tree.
    """
    from gallery_dl import job

    dl = job.DownloadJob(url)
    dl.out = reporter
    return dl.run()


def unsupported_url_error() -> type[Exception]:
    from gallery_dl import exception
    return exception.NoExtractorError

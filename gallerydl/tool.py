# Batch URL Importer — an Atelier Studio plugin
# Copyright (C) 2026 Tejeswaar
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
#
# It links against gallery-dl (GPL-2.0) and is therefore GPL-2.0 too.
# Distributed WITHOUT ANY WARRANTY; see the LICENSE file for details.

"""Batch URL Importer — gallery-dl (GPL-2.0), 150+ gallery sites.

URL Import (core, yt-dlp) answers "give me this video". This answers
"give me all 240 images in this artist's feed" — Pixiv, DeviantArt,
ArtStation, Twitter/X, Reddit, Tumblr, the booru family, manga readers.

They stay two separate tools on purpose: merging them would drag this
GPL-2.0 dependency into a core workflow, and the installer stays
GPL-free. See UNIFIED URL IMPORT in PLANS.txt.

Unlike every other tool in the app this one returns a FOLDER, because
one link legitimately produces hundreds of files. That also means it
cannot be the first step of a pipeline — the tool after it expects a
single file. Import first, then run a tool over what you got.
"""
from pathlib import Path
from typing import Any

from atelier.core.hardware import Hardware
from atelier.tools.base import BaseTool, ParamSpec

_BROWSERS = ("none", "firefox", "chrome", "edge", "brave", "vivaldi",
             "chromium", "safari")


class BatchUrlImportTool(BaseTool):
    id = "gallerydl"
    name = "Batch URL Importer"
    description = ("Paste one gallery link and import the whole set — "
                   "Pixiv, DeviantArt, ArtStation, Twitter/X, Reddit, "
                   "Tumblr and 150+ more. Counts the files before it "
                   "starts, so you know what you asked for. For a single "
                   "video, URL Import is the faster path.")
    input_types = ("url",)

    def params(self) -> list[ParamSpec]:
        return [
            ParamSpec("limit", "Max files", "int", 0, min=0, max=100_000,
                      help="0 = everything the link offers. A busy artist "
                           "feed can be thousands of files and tens of GB, "
                           "so set a number if you only want a sample — "
                           "you always get the newest ones first."),
            ParamSpec("include_video", "Include videos", "bool", True,
                      help="Galleries often mix video in with the images. "
                           "Videos are fetched with the same engine URL "
                           "Import uses, so quality matches."),
            ParamSpec("browser_cookies", "Sign in using browser", "choice",
                      "none", choices=_BROWSERS,
                      help="Private or subscriber-only galleries need a "
                           "login. Pick the browser you are already signed "
                           "in with and this borrows that session. "
                           "Atelier never asks for, stores, or sends your "
                           "password — leave this on 'none' for public "
                           "galleries."),
        ]

    def defaults_for(self, hw: Hardware) -> dict[str, Any]:
        # nothing here touches the GPU: downloading is network + disk,
        # and it runs identically on NVIDIA, AMD, Intel and plain CPU
        return {p.name: p.default for p in self.params()}

    def run(self, ctx, input_path: str, work_dir: str,
            params: dict[str, Any]) -> str:
        try:
            from . import gdl
        except ImportError:  # loaded outside the package (tests, tooling)
            import gdl  # type: ignore

        url = input_path.strip()
        limit = int(params.get("limit", 0) or 0)
        browser = params.get("browser_cookies", "none")

        dest = Path(work_dir) / gdl.folder_name(url)
        dest.mkdir(parents=True, exist_ok=True)

        ffmpeg_dir = ""
        if params.get("include_video", True):
            try:
                from atelier.core.media import ensure_ffmpeg
                ffmpeg, _ = ensure_ffmpeg()
                ffmpeg_dir = str(Path(ffmpeg).parent)
            except Exception as exc:      # images still work without it
                ctx.log(f"ffmpeg unavailable, videos may be skipped: {exc}")

        gdl.configure(dest, limit=limit,
                      include_video=bool(params.get("include_video", True)),
                      browser_cookies="" if browser == "none" else browser,
                      ffmpeg_dir=ffmpeg_dir)

        # 1. count first, downloading nothing — this is why the bar is
        #    honest from the first file instead of sitting at 0%
        ctx.log(f"reading: {url}")
        ctx.progress(0.0, "reading the gallery…")
        total = gdl.count_items(url)
        if total == 0:
            raise RuntimeError(
                "that link has nothing to download. If the gallery is "
                "private, pick your browser under 'Sign in using browser'.")
        if total is None:
            ctx.log("could not count the gallery up front — progress will "
                    "show files done, not a percentage")
        else:
            ctx.log(f"found {total} file{'s' if total != 1 else ''}")
            ctx.progress(0.02, f"0 / {total}")

        # 2. download, reporting through gallery-dl's own output contract
        reporter = _Progress(ctx, total)
        status = gdl.download(url, reporter)

        got = sorted(p for p in dest.rglob("*") if p.is_file())
        if not got:
            raise RuntimeError(
                "nothing was downloaded (gallery-dl status "
                f"{status}). The link may be private, removed, or need a "
                "browser sign-in.")

        size = sum(p.stat().st_size for p in got)
        ctx.log(f"imported {len(got)} file{'s' if len(got) != 1 else ''} · "
                f"{_pretty_size(size)}")
        if reporter.skipped:
            ctx.log(f"{reporter.skipped} already existed and were reused")
        ctx.progress(1.0)
        return str(dest)


def _pretty_size(n: int) -> str:
    """A 400 KB import should not read as '0 MB'."""
    if n >= 1e9:
        return f"{n / 1e9:.1f} GB"
    if n >= 1e6:
        return f"{n / 1e6:.0f} MB"
    return f"{n / 1e3:.0f} KB"


class _Progress:
    """gallery-dl's output contract: the same start/success/skip/progress
    methods its own NullOutput and TerminalOutput implement.

    Two levels at once — which file we are on out of the counted total,
    and how far through the current file. The second level is what stops
    one big video from looking frozen.
    """

    def __init__(self, ctx, total: int | None):
        self.ctx = ctx
        self.total = total
        self.done = 0
        self.skipped = 0
        self.current = ""

    # -- gallery-dl calls these -------------------------------------
    def start(self, path) -> None:
        self.current = Path(str(path)).name
        self._emit()

    def success(self, path) -> None:
        self.done += 1
        self.current = Path(str(path)).name
        self._emit()

    def skip(self, path) -> None:
        self.done += 1
        self.skipped += 1
        self.current = Path(str(path)).name
        self._emit(suffix=" (already had it)")

    def progress(self, bytes_total, bytes_downloaded,
                 bytes_per_second) -> None:
        """Within the current file — only fires once a file is slow
        enough to need it (>1s), so small images never reach here."""
        rate = (f" · {bytes_per_second / 1e6:.1f} MB/s"
                if bytes_per_second else "")
        if bytes_total:
            part = (f" · {bytes_downloaded / 1e6:.0f} of "
                    f"{bytes_total / 1e6:.0f} MB")
        else:
            part = f" · {bytes_downloaded / 1e6:.0f} MB"
        self._emit(suffix=part + rate)

    # -- our side ----------------------------------------------------
    def _emit(self, suffix: str = "") -> None:
        name = self.current[:44]
        if self.total:
            fraction = 0.02 + 0.97 * min(self.done / self.total, 1.0)
            label = f"{self.done} / {self.total} · {name}{suffix}"
        else:
            # unknown total: never fake a percentage, just count up
            fraction = 0.0
            label = f"{self.done} done · {name}{suffix}"
        self.ctx.progress(fraction, label)

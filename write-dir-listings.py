#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2026 Matthias Klumpp <matthias@tenstral.net>
#
# SPDX-License-Identifier: MPL-2.0

"""
Generate a static ``index.html`` directory listing inside every subdirectory
of a given root, suitable for serving as a GitHub Pages site.
"""

import sys
import math
import argparse
from pathlib import Path
from datetime import datetime, timezone

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: Roboto, Arial, sans-serif;
    font-size: 15px;
    background: #f6f8fa;
    color: #24292f;
}
header {
    background: #fff;
    border-bottom: 1px solid #d0d7de;
    padding: 14px 24px;
}
header h1 {
    font-size: 1.1rem;
    font-weight: 600;
    word-break: break-all;
}
header h1 .sep { color: #8c959f; margin: 0 2px; }
main { padding: 24px; max-width: 1024px; margin: 0 auto; }
table {
    width: 100%;
    border-collapse: collapse;
    background: #fff;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    overflow: hidden;
}
thead th {
    text-align: left;
    padding: 10px 16px;
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: .04em;
    color: #57606a;
    background: #f6f8fa;
    border-bottom: 1px solid #d0d7de;
}
tbody tr { border-bottom: 1px solid #eaeef2; }
tbody tr:last-child { border-bottom: none; }
tbody tr:hover { background: #f6f8fa; }
td { padding: 8px 16px; }
td.icon { width: 28px; padding-right: 0; color: #57606a; }
td.name a {
    color: #0969da;
    text-decoration: none;
}
td.name a:hover { text-decoration: underline; }
td.name a.dir { font-weight: 500; }
td.size {
    white-space: nowrap;
    color: #57606a;
    font-size: 0.85rem;
    font-variant-numeric: tabular-nums;
    text-align: right;
}
tr.parent td.name a { color: #57606a; font-style: italic; }
footer {
    margin-top: 18px;
    text-align: center;
    font-size: 0.78rem;
    color: #8c959f;
}
"""

_PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>{css}</style>
</head>
<body>
<header><h1>{breadcrumb}</h1></header>
<main>
<table>
  <thead>
    <tr>
      <th class="icon"></th>
      <th>Name</th>
      <th style="text-align:right">Size</th>
    </tr>
  </thead>
  <tbody>
{rows}  </tbody>
</table>
<footer>Generated {generated}</footer>
</main>
</body>
</html>
"""

_ROW_PARENT = """\
    <tr class="parent">
      <td class="icon">↑</td>
      <td class="name" colspan="3"><a href="../">Parent directory</a></td>
    </tr>
"""

_ROW_DIR = """\
    <tr>
      <td class="icon">📁</td>
      <td class="name"><a class="dir" href="{href}">{name}/</a></td>
      <td class="size">—</td>
    </tr>
"""

_ROW_FILE = """\
    <tr>
      <td class="icon">📄</td>
      <td class="name"><a href="{href}">{name}</a></td>
      <td class="size">{size}</td>
    </tr>
"""

_ROW_PACKAGE = """\
    <tr>
      <td class="icon">📦</td>
      <td class="name"><a href="{href}">{name}</a></td>
      <td class="size">{size}</td>
    </tr>
"""


def _human_size(n_bytes: int) -> str:
    """Return a compact human-readable byte count (e.g. ``1.4 MiB``)."""
    if n_bytes == 0:
        return "0 B"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    idx = min(int(math.log(n_bytes, 1024)), len(units) - 1)
    value = n_bytes / (1024**idx)
    return f"{value:.1f} {units[idx]}" if idx else f"{n_bytes} B"


def _breadcrumb(directory: Path, root: Path) -> str:
    """Build an HTML breadcrumb relative to *root*."""
    try:
        rel = directory.relative_to(root)
    except ValueError:
        rel = directory

    parts = list(rel.parts)
    if not parts:
        return "<strong>/</strong>"

    crumbs: list[str] = ['<a href="' + "../" * len(parts) + '">💠</a>']
    for i, part in enumerate(parts):
        if i < len(parts) - 1:
            depth = len(parts) - i - 1
            crumbs.append(f'<a href="{"../" * depth}">{part}</a>')
        else:
            crumbs.append(f"<strong>{part}</strong>")

    return '<span class="sep"> / </span>'.join(crumbs)


def generate_index(directory: Path, root: Path, is_root: bool) -> None:
    """Write ``index.html`` for *directory*."""
    entries = sorted(
        (e for e in directory.iterdir() if not e.name.startswith(".")),
        key=lambda e: (not e.is_dir(), e.name.lower()),
    )

    rows: list[str] = []

    if not is_root:
        rows.append(_ROW_PARENT)

    for entry in entries:
        if entry.name == "index.html":
            continue
        if entry.is_dir():
            rows.append(_ROW_DIR.format(href=f"{entry.name}/", name=entry.name))
        else:
            file_tmpl = _ROW_PACKAGE if entry.suffix == ".deb" else _ROW_FILE
            rows.append(
                file_tmpl.format(
                    href=entry.name,
                    name=entry.name,
                    size=_human_size(entry.stat().st_size),
                )
            )

    try:
        title_path = "/" + str(directory.relative_to(root))
    except ValueError:
        title_path = "/"
    if title_path == "/.":
        title_path = "/"

    html = _PAGE.format(
        title=title_path,
        css=_CSS,
        breadcrumb=_breadcrumb(directory, root),
        rows="".join(rows),
        generated=datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )

    index_file = directory / "index.html"
    index_file.write_text(html, encoding="utf-8")


def generate_listings(root: Path) -> int:
    """
    Walk "root" and write an ``index.html`` into every directory found.
    Returns the number of files written.
    """
    count = 0
    generate_index(root, root, is_root=True)
    count += 1

    for dirpath, dirnames, _ in root.walk(top_down=True):
        # Skip hidden directories in-place so os.walk won't descend into them.
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for dirname in dirnames:
            subdir = Path(dirpath) / dirname
            generate_index(subdir, root, is_root=False)
            count += 1

    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate static index.html directory listings.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        metavar="DIR",
        help="Root directory to index",
    )
    args = parser.parse_args(argv)

    if not args.root.is_dir():
        print(f"error: directory not found: {args.root}", file=sys.stderr)
        return 1

    n = generate_listings(args.root)
    print(f"Generated {n} index.html file(s) under {args.root}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())

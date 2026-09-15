#!/usr/bin/env python3
"""
apply_overrides.py — точечные ручные правки поверх результата импорта.

Источник правды — data/overrides.json:

    { "<арка>": { "<файл без .md>": { "title": "...", "phase": N, "label": "..." } } }

Патчит frontmatter в content/arc-NN/<файл>.md и соответствующую строку в
content/arc-NN/_manifest.json. Идемпотентно. Запускать после set_phases.py
(уже включено в tools/import_all.py как последний пост-шаг).

    python tools/apply_overrides.py
    python tools/apply_overrides.py --dry-run
    python tools/apply_overrides.py --arc 9
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import arc_folder, force_utf8_stdout, frontmatter, write_text_lf

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ("title", "phase", "label", "volume", "number")


def parse_fm(fm: str) -> dict:
    """frontmatter в нашем формате `ключ: <json>` → dict."""
    meta: dict = {}
    for line in fm.splitlines():
        m = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if not m:
            continue
        k, raw = m.group(1), m.group(2).strip()
        try:
            meta[k] = json.loads(raw)
        except Exception:
            meta[k] = raw.strip('"')
    return meta


def patch_md(md: Path, patch: dict, dry: bool) -> bool:
    text = md.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        print(f"  ! {md.name}: не разобрал frontmatter")
        return False
    meta = parse_fm(m.group(1))
    changed = False
    for k, v in patch.items():
        if meta.get(k) != v:
            meta[k] = v
            changed = True
    if changed and not dry:
        write_text_lf(md, f"---\n{frontmatter(meta)}\n---\n{m.group(2)}")
    return changed


def main() -> None:
    force_utf8_stdout()
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--content", type=Path, default=ROOT / "content")
    ap.add_argument("--overrides", type=Path, default=ROOT / "data" / "overrides.json")
    ap.add_argument("--arc", nargs="*", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.overrides.exists():
        print(f"нет {args.overrides} — пропуск")
        return

    data = json.loads(args.overrides.read_text("utf-8"))
    total = 0
    for arc_key, files in data.items():
        if arc_key.startswith("_"):
            continue
        if args.arc and arc_key not in args.arc:
            continue
        folder = args.content / arc_folder(arc_key)
        if not folder.exists():
            print(f"арка {arc_key}: нет папки {folder} — пропуск")
            continue

        mf = folder / "_manifest.json"
        manifest = json.loads(mf.read_text("utf-8")) if mf.exists() else None
        rows = manifest.get("chapters", []) if manifest else []

        n = 0
        for stem, raw_patch in files.items():
            patch = {k: v for k, v in raw_patch.items() if k in FIELDS}
            if not patch:
                continue
            md = folder / f"{stem}.md"
            if not md.exists():
                print(f"  ! арка {arc_key}: нет {md.name}")
                continue
            if patch_md(md, patch, args.dry_run):
                n += 1
            for r in rows:
                if r.get("slug") == stem:
                    r.update(patch)

        if manifest and rows and not args.dry_run:
            manifest["chapters"] = rows
            write_text_lf(mf, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        print(f"арка {arc_key}: {'изменит' if args.dry_run else 'изменено'} {n} файлов")
        total += n

    print(f"\nвсего: {total}" + ("  (--dry-run)" if args.dry_run else ""))


if __name__ == "__main__":
    main()

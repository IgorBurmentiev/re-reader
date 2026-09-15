#!/usr/bin/env python3
"""
import_all.py — один прогон: все источники → content/arc-NN/ + content/_pending/.

Оркестратор: вызывает fb2/epub/pdf-конвертеры с нужными аргументами по каждой
арке. Многотомные арки (2, 3) собираются в одну папку через --append со сквозной
нумерацией; тома различаются полем volume во frontmatter.

    python tools/import_all.py                    # всё, кроме OCR-хвоста 4.5
    python tools/import_all.py --only 7 9 10      # только эти арки
    python tools/import_all.py --with-ocr         # + арка 4.5 (медленно)
    python tools/import_all.py --clean            # снести целевые папки перед импортом

После импорта запусти  python tools/validate.py
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import arc_folder as _arc_folder  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "sources"
PY = [sys.executable]


def fb2(*a): return ["tools/fb2_to_md.py", *a]
def epub(*a): return ["tools/epub_to_md.py", *a]
def pdf(*a): return ["tools/pdf_to_md.py", *a]


def _ln(v: int) -> str:
    return str(next((SRC / "ln").rglob(f"Том {v} *.fb2")))


# арка -> список шагов (каждый шаг — argv конвертера без python и без --out)
def plan(content: Path, with_ocr: bool) -> dict[str, list[list[str]]]:
    a = lambda n: str(content / f"arc-{n}")                       # noqa: E731
    P: dict[str, list[list[str]]] = {
        "1": [fb2(_ln(1), "--arc", "1", "--volume", "1", "--out", a("01"))],
        "2": [
            fb2(_ln(2), "--arc", "2", "--volume", "2", "--out", a("02")),
            fb2(_ln(3), "--arc", "2", "--volume", "3", "--append", "--out", a("02")),
        ],
        "3": [
            fb2(_ln(4), "--arc", "3", "--volume", "4", "--out", a("03")),
            *[fb2(_ln(v), "--arc", "3", "--volume", str(v), "--append", "--out", a("03"))
              for v in (5, 6, 7, 8, 9)],
        ],
        "4": [pdf(str(SRC / "wn/arc4/Арка 4 + 4.5 ReZero.pdf"),
                  "--arc", "4", "--text-pages", "1-1737", "--out", a("04"))],
        "5": [epub(str(SRC / "wn/arc5/5 арка.epub"), "--arc", "5", "--out", a("05"))],
        "6": [pdf(str(SRC / "wn/arc6/Арка 6 Re_Zero.pdf"), "--arc", "6", "--out", a("06"))],
        "7": [fb2(str(SRC / "wn/arc7/Арка 7 Главы 1-110 ReZero.fb2"),
                  "--arc", "7", "--out", a("07"))],
        "8": [fb2(str(SRC / "wn/arc8/8 арка Главы 1-74 + интерлюдия ReZero.fb2"),
                  "--arc", "8", "--out", a("08"))],
        "9": [epub(str(SRC / "wn/arc9/9_арка,_Главы_1_59_+_Интерлюдии_+_Финал_+_Побочные_истории.epub"),
                   "--arc", "9", "--out", a("09"))],
        "10": [
            epub(str(SRC / "wn/arc10/Арка_10,_главы_1_24,_прологи,_интерлюдии.epub"),
                 "--arc", "10", "--out", a("10")),
            epub(str(SRC / "wn/arc10/arc10_ongoing"), "--arc", "10", "--phase", "3",
                 "--order-from-filename", "--append", "--out", a("10")),
        ],
    }
    if with_ocr:
        # One Day II — не арка, а побочная история (ТЗ §6.4): в _pending
        P["4.5"] = [pdf(str(SRC / "wn/arc4/Арка 4 + 4.5 ReZero.pdf"), "--arc", "4",
                        "--ocr-pages", "1738-1830", "--ocr-only",
                        "--side-story", "One Day II", "--read-after", "4:6",
                        "--out", str(content / "_pending"))]
    return P


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--content", type=Path, default=ROOT / "content")
    ap.add_argument("--only", nargs="*", default=None, help="только эти арки")
    ap.add_argument("--with-ocr", action="store_true", help="+ OCR-хвост арки 4.5")
    ap.add_argument("--clean", action="store_true", help="снести целевые папки перед импортом")
    ap.add_argument("--skip-post", action="store_true",
                    help="без пост-обработки (set_phases / synopses / arcs.json)")
    ap.add_argument("--dry-run", action="store_true", help="показать команды, не запускать")
    args = ap.parse_args()

    P = plan(args.content, args.with_ocr)
    arcs = args.only or list(P)
    arcs = [x for x in arcs if x in P]

    if args.clean and not args.dry_run:
        for x in arcs:
            for d in (args.content / _arc_folder(x), args.content / f"arc-{x}"):
                if d.exists():
                    shutil.rmtree(d)
        if set(arcs) & {"9", "10", "4.5"} and (args.content / "_pending").exists():
            shutil.rmtree(args.content / "_pending")
        for stale in ("arc-04-5", "arc-4.5"):          # прежнее место One Day II
            if (args.content / stale).exists():
                shutil.rmtree(args.content / stale)

    failed = []
    for x in arcs:
        print(f"\n{'=' * 70}\n  АРКА {x}\n{'=' * 70}")
        for step in P[x]:
            cmd = PY + step
            print("  $ " + " ".join(f'"{c}"' if " " in c else c for c in cmd[1:]))
            if args.dry_run:
                continue
            r = subprocess.run(cmd, cwd=ROOT)
            if r.returncode != 0:
                failed.append((x, step[0]))
                print(f"  !! шаг завершился с кодом {r.returncode}")
                break

    if failed:
        print(f"\n{'=' * 70}\nСБОЙ:", failed)
        sys.exit(1)

    if not args.dry_run and not args.skip_post:
        print(f"\n{'=' * 70}\n  ПОСТ-ОБРАБОТКА\n{'=' * 70}")
        for post in (["tools/set_phases.py"],
                     ["tools/apply_overrides.py"],   # ручные правки поверх — после фаз
                     ["tools/build_synopses.py"],
                     ["tools/build_arcs_json.py"]):
            print("  $ " + " ".join(post))
            subprocess.run(PY + post, cwd=ROOT)

    print(f"\n{'=' * 70}\nГотово. Проверка:  python tools/validate.py")


if __name__ == "__main__":
    main()

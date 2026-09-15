#!/usr/bin/env python3
"""
upscale.py — разовый апскейл мелких картинок через Real-ESRGAN (ТЗ §8).

Обложки/заставки и часть внутренних иллюстраций в источниках маленькие
(736 px и т.п.), Astro их не растягивает. Этот шаг догоняет их до разумного
размера аниме-моделью Real-ESRGAN (ncnn-vulkan, GPU), затем аккуратно ужимает
Ланцошем до целевого размера и пережимает.

Идемпотентно: оригинал кладётся в <папка>/_orig/, повторный прогон такие пропускает.

    python tools/upscale.py covers          # assets/covers/** (по умолчанию)
    python tools/upscale.py illos           # content/arc-*/images/**
    python tools/upscale.py covers illos --min 1100
    python tools/upscale.py covers --force  # переделать уже обработанные

После: пересобрать сайт (npm run build).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Нужен pillow:  pip install pillow")

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "tools" / "vendor" / "realesrgan" / "realesrgan-ncnn-vulkan.exe"
MODEL = "realesrgan-x4plus-anime"   # модель ТОЛЬКО 4x — гоняем всегда на -s 4,
                                    # нужный размер добираем Ланцошем (см. process)
GPU = "1"                           # GPU 0 (AMD iGPU) даёт битую «мозаику»; 1 = NVIDIA

# профили: папка, glob, максимум любой стороны, и функция «нужен ли апскейл»
def _need_cover(path: Path, w: int, h: int) -> int | None:
    """→ желаемая короткая сторона, если апскейл нужен; иначе None."""
    name = path.name.lower()
    if "card" in name:                       # карточка ~500px на 2× → нужен ~1000+
        return 1050 if (w < 1050 or h < 680) else None
    # hero / site-hero — широкий баннер, высота под градиентом, ширина важнее
    return 1400 if (w < 1500 or h < 480) else None


def _need_illo(path: Path, w: int, h: int) -> int | None:
    short = min(w, h)
    return 1100 if short < 850 else None


PROFILES = {
    "covers": (ROOT / "assets" / "covers", "**/*.[jp][pn]g", 2560, _need_cover),
    "illos": (ROOT / "content", "arc-*/images/*.[jp][pn]*g", 2200, _need_illo),
}


def run_esrgan(src: Path, dst: Path, scale: int) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [str(BIN), "-i", str(src), "-o", str(dst),
         "-n", MODEL, "-s", str(scale), "-g", GPU, "-f", "png"],
        check=True, capture_output=True,
    )


def process(img_path: Path, need_fn, cap: int, force: bool) -> str:
    orig_dir = img_path.parent / "_orig"
    backup = orig_dir / img_path.name
    if backup.exists() and not force:
        return "skip (уже обработан)"

    src = backup if backup.exists() else img_path
    with Image.open(src) as im:
        w, h = im.size
        has_alpha = im.mode in ("RGBA", "LA") or "transparency" in im.info

    target_min = need_fn(img_path, w, h)
    if target_min is None:
        return f"skip ({w}x{h} — норм)"

    if not backup.exists():
        orig_dir.mkdir(exist_ok=True)
        backup.write_bytes(src.read_bytes())

    with tempfile.TemporaryDirectory() as td:
        big = Path(td) / "big.png"
        run_esrgan(backup, big, 4)          # всегда 4x — модель другого не умеет
        with Image.open(big) as up:
            bw, bh = up.size
            # целевой размер: короткая сторона = target_min, но длинная ≤ cap
            k = target_min / min(bw, bh)
            if max(bw, bh) * k > cap:
                k = cap / max(bw, bh)
            tw, th = max(1, round(bw * k)), max(1, round(bh * k))
            out = up.resize((tw, th), Image.LANCZOS) if (tw, th) != (bw, bh) else up
            if img_path.suffix.lower() in (".jpg", ".jpeg"):
                out.convert("RGB").save(img_path, "JPEG", quality=88,
                                        subsampling=1, optimize=True)
            else:
                (out if has_alpha else out.convert("RGB")).save(
                    img_path, "PNG", optimize=True)
    return f"{w}x{h} → {tw}x{th}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("targets", nargs="*", help="covers | illos (по умолчанию covers)")
    ap.add_argument("--min", type=int, default=None, help="желаемая короткая сторона")
    ap.add_argument("--cap", type=int, default=None, help="максимум любой стороны")
    ap.add_argument("--force", action="store_true", help="переделать обработанные")
    ap.add_argument("--gpu", default=GPU,
                    help="индекс GPU для realesrgan (0 = AMD iGPU — БАГОВАННЫЙ, 1 = NVIDIA)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    globals()["GPU"] = args.gpu

    if not BIN.exists():
        sys.exit(f"Не найден {BIN}\n"
                 "Скачай realesrgan-ncnn-vulkan (windows zip) в tools/vendor/realesrgan/")

    targets = args.targets or ["covers"]
    bad = [t for t in targets if t not in PROFILES]
    if bad:
        sys.exit(f"неизвестные цели: {bad}; доступно: {list(PROFILES)}")
    total = done = 0
    for name in targets:
        base, pat, dcap, need_fn = PROFILES[name]
        dcap = args.cap or dcap
        if args.min:
            _mn = args.min
            need_fn = lambda p, w, h, _b=need_fn: (_mn if _b(p, w, h) else None)  # noqa: E731
        files = [f for f in sorted(base.glob(pat)) if "_orig" not in f.parts]
        print(f"\n[{name}] {base}  ({len(files)} файлов, cap {dcap})")
        for f in files:
            total += 1
            if args.dry_run:
                with Image.open(f) as im:
                    w, h = im.size
                tgt = need_fn(f, w, h)
                print(f"  {f.relative_to(ROOT)}  {w}x{h}  "
                      + (f"→ апскейл до ≥{tgt}" if tgt else "ok"))
                continue
            try:
                msg = process(f, need_fn, dcap, args.force)
            except subprocess.CalledProcessError as e:
                msg = f"! ошибка esrgan: {e.stderr.decode('utf-8', 'replace')[:120]}"
            if not msg.startswith("skip"):
                done += 1
            print(f"  {f.relative_to(ROOT)}: {msg}")
    print(f"\nобработано {done} из {total}"
          + ("  (--dry-run)" if args.dry_run else ""))


if __name__ == "__main__":
    main()

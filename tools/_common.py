#!/usr/bin/env python3
"""
_common.py — общий слой для всех четырёх конвертеров читалки.

Здесь живёт то, что обязано совпадать между fb2/epub/pdf/import-конвертерами:
нормализация типографики, модель главы, определение типа и номера по заголовку,
сквозная нумерация с отчётом об аномалиях, запись .md с frontmatter и
спойлер-безопасный вывод (в консоль — только цифры, названия по флагу).

Ничего не печатает при импорте. Все функции чистые, кроме write_chapter/Reporter.
"""

from __future__ import annotations

import html
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


# ─────────────────────────── консоль ───────────────────────────

def force_utf8_stdout() -> None:
    """Windows-консоль по умолчанию cp1251/cp1252 и падает на кириллице в print().
    Зовётся первой строкой в main() каждого конвертера."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # py3.7+
        except (AttributeError, ValueError):
            pass


# ─────────────────────────── типографика ───────────────────────────

SCENE_BREAK = "<hr class='scene-break' />"

# строки-разделители сцен в источниках: звёздочки, ромбики, тире-цепочки
_SCENE_RE = re.compile(
    r"^[\s]*(?:[*※＊✽✼❋·•∙◦●○◆◇■□▲△▼▽]|[-–—]{3,}|△▼|▼△){2,}[\s]*$"
)
_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def is_scene_break(line: str) -> bool:
    return bool(_SCENE_RE.match(line.strip()))


def is_cjk_only(line: str) -> bool:
    """Строка состоит только из иероглифов/каны и пунктуации — японский подзаголовок."""
    s = re.sub(r"[\s\W]", "", line, flags=re.UNICODE)
    return bool(s) and all(_CJK_RE.match(ch) for ch in s)


# мусор редакторов и переводческие пометки, попавшие в текст (особенно из PDF)
_JUNK_LINE = re.compile(
    r"^\s*(?:"
    r"fb2edit\b.*"
    r"|(?:после|перед)\s+\d+[-\s]*(?:й|ой|ую)?\s*глав\w*\s+чита\w+.*"
    r"|\S+\s+\d{4}-\d\d-\d\d\s+\d\d:\d\d:\d\d\s*$"
    r"|https?://\S+\s*$"
    r")\s*$",
    re.I,
)
_JUNK_TAIL = re.compile(r"\s*fb2edit\b[^\n]*$", re.I)


def strip_junk(text: str) -> str:
    """Убирает строки-подписи редакторов и переводческие пометки о порядке чтения."""
    text = _JUNK_TAIL.sub("", text)
    return "\n".join(ln for ln in text.split("\n") if not _JUNK_LINE.match(ln))


def deshout(s: str) -> str:
    """«МОЛИТВЫ, КАК ОБЛАКА» → «Молитвы, как облака». Латинские куски (NO STELLA
    NO LIFE) не трогаем. Имена внутри теряют заглавную — правится точечно."""
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return s
    cyr = [c for c in letters if "а" <= c.lower() <= "я" or c in "ёЁ"]
    if len(cyr) < 4 or sum(c.isupper() for c in cyr) / len(cyr) < 0.7:
        return s
    # sentence-case: заглавная только в начале и после . ! ? …
    # (имена собственные внутри теряют заглавную — правится точечно в тексте главы)
    out, cap = [], True
    for ch in s.lower():
        out.append(ch.upper() if (cap and ch.isalpha()) else ch)
        if ch.isalpha():
            cap = False
        elif ch in ".!?…":
            cap = True
    return "".join(out)


def normalize_typography(text: str) -> str:
    """Единые правила из ТЗ §4. Применяется к готовому телу главы (Markdown-абзацы
    уже разделены пустой строкой)."""
    text = html.unescape(text)
    text = re.sub(r"&quot;?", '"', text)
    text = strip_junk(text)
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CTRL_RE.sub("", text)
    text = text.replace(" ", " ")
    # невидимые распорки: hangul filler, zwsp/zwj, braille blank
    text = re.sub("[ᅟᅠ​-‏ ⁠⠀ㅤ﻿]", "", text)
    text = html.unescape(text)                       # &quot; &laquo; &mdash; …
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\.\.\.+", "…", text)
    text = text.replace("\u2026.", "…").replace(".\u2026", "…")
    # реплики: одиночные -/– в начале строки → длинное тире
    text = re.sub(r"^[ \t]*[-–][ \t]+", "— ", text, flags=re.M)
    # тире в середине предложения: « слово - слово » → длинное тире
    text = re.sub(r"(?<=\S) [-–] (?=\S)", " — ", text)
    # прямые кавычки → «ёлочки» (парами, не жадно, в пределах абзаца)
    text = re.sub(r'"([^"\n]+)"', r"«\1»", text)
    # неразрывные пробелы после однобуквенных предлогов/союзов
    text = re.sub(r"(?<=\s)([а-яёА-ЯЁ])[ ]+", "\\1\u00a0", text)
    text = re.sub(r"[ ]+([—])", "\u00a0\\1", text)   # тире не отрывается от слова слева
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def paragraphs(body: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]


def trim_scene_breaks(body: str) -> str:
    """Убирает разделители сцен, повисшие в самом начале/конце главы."""
    ps = paragraphs(body)
    while ps and (ps[0] == SCENE_BREAK or is_scene_break(ps[0])):
        ps.pop(0)
    while ps and (ps[-1] == SCENE_BREAK or is_scene_break(ps[-1])):
        ps.pop()
    return "\n\n".join(ps)


CIRCLED_TO_INT = {c: i for i, c in enumerate("①②③④⑤⑥⑦⑧⑨⑩", 1)}


# ─────────────────────────── заголовки глав ───────────────────────────

# Синонимы типов: как встречается → канон. Порядок важен (финал раньше главы).
_AP = r"^(?:арка\s*\d+\s*[—–\-,]?\s*)?"     # необязательный префикс «Арка N —»
_SPECIALS: list[tuple[re.Pattern, str]] = [
    (re.compile(_AP + r"(?:пролог|prologue)\b", re.I), "prologue"),
    (re.compile(_AP + r"(?:эпилог|epilogue)\b", re.I), "epilogue"),
    (re.compile(_AP + r"(?:финал|конец|заключение|"
                r"curtain'?s?\s+close|reweave|final)\b", re.I), "epilogue"),
    (re.compile(_AP + r"(?:интерлюдия|интермедия|interlude)\b", re.I), "interlude"),
    (re.compile(r"^(?:побочная\s+истори[яи]|side\s*story|ex[\s\-]?новелла|"
                r"короткая\s+истори[яи]|фрагмент|осколок\b)", re.I), "side"),
    # «если» само по себе слишком частое в прозе — только явный IF-маркер
    (re.compile(r"^(?:if[\s:—\-]|if[-_]?истори|если\s*[:\-—])", re.I), "if"),
    (re.compile(r"^(?:послесловие|afterword|postscript|постскриптум|бонус|"
                r"иллюстрац|начальные\s+иллюстрации|author'?s?\s+note)\b", re.I), "extra"),
]

# «Глава 54B», «Глава 2.5», «Глава 123 (A)», «Chapter 7», «ГЛАВА 1», «Арка 8 — Глава 3»
# Буква ветки (A/B/А/В/Б) — только приклеенная к цифрам (54B) или в скобках (123 (A)).
# Через пробел — НЕ ветка, а первое слово названия («Глава 7 Воссоединение»).
_BR = "ABАВБabавб"       # лат./кир. A B А В Б
_BRANCH = r"(?:[" + _BR + r"]\b|\s*\(\s*[" + _BR + r"]\s*\))"
_DASH = r"[—–\-]"        # em-dash, en-dash, hyphen
_CHAPTER_RE = re.compile(
    r"^(?:арк[аи]\s*\d+(?:[.,]\d+)?\s*[—–\-,:]?\s*)?"
    r"(?:глава|chapter|гл\.?)\s*"
    r"№?\s*"
    r"(?P<num>\d+(?:[.,]\d+)?" + _BRANCH + r"?)"
    r"\s*[.:,)»\"”—\-]*\s*"
    r"(?P<title>.*)$",
    re.I,
)
_PHASE_RE = re.compile(r"^фаза\s*(?P<num>\d+)\b", re.I)

_KIND_ORDER = {"prologue": 0, "chapter": 1, "interlude": 2, "epilogue": 3,
               "side": 4, "if": 5, "extra": 6}


# кириллические А/В/С/Е выглядят как латинские — приводим ветку к латинице,
# чтобы «123 (А)» из источника и «123 (A)» из arcs.md были одним и тем же
_CYR2LAT = str.maketrans("АВСЕ", "ABCE")


def normalize_label(num: str) -> str:
    """'54b' → '54B' (приклеенная буква как в источнике: ТЗ пишет «54B»),
    '123 ( а )' → '123 (A)' (форма со скобками сохраняется), '2,5' → '2.5'."""
    paren = "(" in num
    s = re.sub(r"\s+", "", num).replace(",", ".").replace("(", "").replace(")", "").upper()
    s = s.translate(_CYR2LAT)
    m = re.match(r"^(\d+(?:\.\d+)?)([ABCЕ]?)$", s)
    if not m:
        return s
    base, branch = m.groups()
    if not branch:
        return base
    return f"{base} ({branch})" if paren else f"{base}{branch}"


_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
_QUOTE_PAIRS = {"«": "»", "“": "”", '"': '"', "„": "“", "‘": "’"}


def _trim_title(s: str) -> str:
    """Убирает служебный хвост после номера (разделители, пробелы) и кавычки-обёртку
    всего названия, но НЕ трогает внутренние кавычки («Ведьмак» против «Ведьмы»)."""
    s = html.unescape(s or "")
    s = re.sub(r"&quot;?", '"', s)
    s = deshout(s.strip())
    s = s.strip().lstrip(" .:,;—–-").strip()
    if not (s.endswith("...") or s.endswith("…")):
        s = s.rstrip(" .:,;—–-").strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"' and s.count('"') == 2:
        s = s[1:-1].strip()
    elif len(s) >= 2 and s[0] == "«" and s[-1] == "»" and s.count("«") == 1:
        s = s[1:-1].strip()
    elif len(s) >= 2 and s[0] == "“" and s[-1] == "”" and s.count("“") == 1:
        s = s[1:-1].strip()
    return s


def classify_heading(text: str) -> dict | None:
    """text → {'kind','label','title'} либо None, если это не заголовок.

    label — номер как в источнике (строка!) или '' для безномерных типов.
    """
    t = re.sub(r"\s+", " ", (text or "")).strip().strip("*_#").strip()
    if not t or len(t) > 200:
        return None

    ph = _PHASE_RE.match(t)
    if ph:
        return {"kind": "phase", "label": ph.group("num"), "title": ""}

    m = _CHAPTER_RE.match(t)
    if m:
        title = _trim_title(m.group("title"))
        if is_cjk_only(title):
            title = ""
        return {"kind": "chapter", "label": normalize_label(m.group("num")), "title": title}

    for rx, kind in _SPECIALS:
        mrx = rx.match(t)
        if mrx:
            # вытащить хвост как название: «Интерлюдия, Катя Орели» / «ФИНАЛ REWEAVE»
            rest = rx.sub("", t, count=1).strip("".join([" ", _CIRCLED]))
            circ = "".join(c for c in t if c in _CIRCLED)
            # «Интерлюдия 2: Приятного аппетита» → label='2', title='Приятного…'
            nm = re.match(r"^(\d+)\s*[:.\-—–]?\s*(.*)$", rest)
            if nm:
                circ = circ or nm.group(1)
                rest = nm.group(2)
            rest = _trim_title(rest)
            if is_cjk_only(rest):
                rest = ""
            # защита от ложных срабатываний на середине абзаца
            # («Конец совместной судьбы Субару…» — это предложение, не заголовок)
            if kind != "side" and rest and rest[:1].islower():
                return None
            if len(t) > 90 and kind != "side":
                return None
            # слово-маркер из источника («Фрагмент», «Пролог», «Финал», «Интермедия»)
            # — чтобы в оглавлении показывать его, а не generic «Побочная»
            kw = re.sub(r"^арк[аи]\s*\d+\s*[—–\-,]?\s*", "", mrx.group(0), flags=re.I)
            kw = kw.strip(" .:,—–-").capitalize()
            return {"kind": kind, "label": circ or kw, "title": rest}
    return None


def looks_like_heading(text: str, *, max_len: int = 120) -> bool:
    """Быстрый предикат для потоковых сканеров (pdf/fb2 без разметки).
    Строже classify_heading: требует короткую строку и осмысленный маркер."""
    t = (text or "").strip()
    if not t or len(t) > max_len:
        return False
    info = classify_heading(t)
    if info is None:
        return False
    if info["kind"] == "chapter":
        return True
    # для безномерных — не хватать середину предложения («конец истории …»)
    return len(t) <= 60 or t.isupper()


# ─────────────────────────── модель главы ───────────────────────────

@dataclass
class Chapter:
    kind: str                       # chapter | prologue | epilogue | interlude | side | if | extra
    label: str = ""                 # номер как в источнике: '2.5', '54B', '123 (A)', ''
    title: str = ""
    body: str = ""                  # Markdown-тело (без заголовка)
    number: str | None = None       # фактический порядковый (строка), проставляется assign_numbers
    volume: int | None = None
    phase: int | None = None
    illustrations: list[str] = field(default_factory=list)
    source: str = ""
    translator: str = ""
    source_ref: str = ""            # откуда извлечено (файл/спайн) — для отчёта, не во frontmatter
    order_release: int | None = None
    order_chrono: int | None = None

    @property
    def words(self) -> int:
        return len(self.body.split())

    @property
    def n_paragraphs(self) -> int:
        return len(paragraphs(self.body))


def assign_numbers(chapters: list[Chapter], *, offset: int = 0,
                   order_offset: int = 0) -> dict:
    """Проставляет number сквозной нумерацией по главам типа chapter.
    Не доверяет source-номерам: number — это просто счётчик, поэтому сбитая
    нумерация в источнике (дубль+пропуск) не ломает ссылки.
    order_offset — сдвиг order_release при дозаписи к существующей арке
    (иначе тома/фазы перемешиваются, т.к. каждый прогон нумерует с 1).
    Возвращает отчёт об аномалиях для печати.
    """
    n = offset
    seen_labels: dict[str, int] = {}
    dups, gaps, nonstd = [], [], []
    prev_int = None
    for idx, ch in enumerate(chapters):
        ch.order_release = order_offset + idx + 1
        ch.order_chrono = ch.order_release
        if ch.kind != "chapter":
            ch.number = None
            continue
        n += 1
        ch.number = str(n)
        lbl = ch.label
        if lbl:
            if lbl in seen_labels:
                dups.append((lbl, seen_labels[lbl], idx))
            seen_labels[lbl] = idx
            base = re.match(r"^(\d+)", lbl)
            if base:
                cur = int(base.group(1))
                if prev_int is not None and cur > prev_int + 1:
                    gaps.extend(range(prev_int + 1, cur))
                prev_int = max(prev_int or 0, cur)
            if re.search(r"[.]|\(|[" + _BR + r"]$", lbl):
                nonstd.append(lbl)
    return {
        "chapters": n - offset,
        "dup_labels": dups,
        "gap_labels": sorted(set(gaps)),
        "nonstandard": nonstd,
        "shift_suspected": bool(dups and gaps),
    }


# ─────────────────────────── запись ───────────────────────────

_FM_ORDER = ["arc", "volume", "phase", "type", "number", "label", "title",
             "order_release", "order_chrono", "illustrations", "source", "translator"]


def frontmatter(meta: dict) -> str:
    lines = []
    for k in _FM_ORDER:
        v = meta.get(k)
        if v in (None, "", []):
            continue
        if isinstance(v, (str, list)):
            lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
        else:
            lines.append(f"{k}: {v}")
    return "\n".join(lines)


def write_text_lf(path: Path, data: str) -> None:
    """Пишем всегда с LF (иначе Windows подставляет CRLF — мусор в git и парсерах)."""
    path.write_text(data, encoding="utf-8", newline="\n")


def chapter_slug(ch: Chapter, index: int, *, nested: bool = False) -> str:
    if ch.kind == "chapter" and ch.number is not None:
        if nested and ch.volume:
            return f"v{int(ch.volume):02d}-c{int(ch.number):03d}"
        return f"{int(ch.number):03d}" if ch.number.isdigit() else re.sub(r"\W+", "-", ch.number)
    tag = {"prologue": "prologue", "epilogue": "epilogue", "interlude": "interlude",
           "side": "side", "if": "if", "extra": "extra"}.get(ch.kind, ch.kind)
    return f"{tag}-{index:02d}"


def write_chapter(out: Path, ch: Chapter, arc: int, *, nested: bool = False,
                  index: int = 0, image_prefix: str = "./images/") -> str:
    out.mkdir(parents=True, exist_ok=True)
    slug = chapter_slug(ch, index, nested=nested)
    meta = {
        "arc": arc, "volume": ch.volume, "phase": ch.phase, "type": ch.kind,
        "number": ch.number, "label": ch.label if ch.label != ch.number else "",
        "title": ch.title, "order_release": ch.order_release,
        "order_chrono": ch.order_chrono, "illustrations": ch.illustrations,
        "source": ch.source, "translator": ch.translator,
    }
    body = re.sub(r"@@IMAGE:([^@]+)@@",
                  lambda m: f"![]({image_prefix}{m.group(1)})", ch.body)
    write_text_lf(out / f"{slug}.md",
                  f"---\n{frontmatter(meta)}\n---\n\n"
                  + "\n\n".join(paragraphs(body)) + "\n")
    return slug


def image_anchors(body: str) -> list[dict]:
    """[{image, after_paragraph}] — к какому абзацу привязана иллюстрация.
    Позволяет подменить картинку на качественную, не трогая текст главы (ТЗ §4)."""
    anchors: list[dict] = []
    n = 0
    for p in paragraphs(body):
        m = re.match(r"^(?:!\[\]\([^)]*\)|@@IMAGE:([^@]+)@@)$", p.strip())
        if m:
            name = m.group(1) or re.search(r"/([^/)]+)\)", p).group(1)
            anchors.append({"image": name, "after_paragraph": n})
        else:
            n += 1
    return anchors


def manifest_rows(chapters: list[Chapter], *, start: int = 0,
                  nested: bool = False, slugs: list[str] | None = None) -> list[dict]:
    rows = []
    for i, c in enumerate(chapters):
        rows.append({
            "slug": slugs[i] if slugs else chapter_slug(c, start + i, nested=nested),
            "type": c.kind,
            "number": c.number, "label": c.label, "title": c.title,
            "phase": c.phase, "volume": c.volume,
            "words": c.words, "paragraphs": c.n_paragraphs,
            "illustrations": c.illustrations,
            "illustration_anchors": image_anchors(c.body),
            "source_ref": c.source_ref.strip(),
        })
    return rows


def write_manifest_rows(out: Path, rows: list[dict], extra: dict | None = None) -> None:
    data = dict(extra or {})
    data["chapters"] = rows
    write_text_lf(out / "_manifest.json",
        json.dumps(data, ensure_ascii=False, indent=2))


def write_manifest(out: Path, chapters: list[Chapter], extra: dict | None = None) -> None:
    write_manifest_rows(out, manifest_rows(chapters), extra)


def _img_ext(name: str) -> str:
    return (Path(name).suffix.lower().replace(".jpeg", ".jpg") or ".jpg")


def finalize_write(out: Path, chapters: list[Chapter], arc: int, *,
                   images: dict[str, bytes], generator: str,
                   sources: list[str], append: bool = False, nested: bool = False,
                   orphan_images: set[str] | None = None,
                   extra: dict | None = None) -> tuple[int, int]:
    """Общий финал всех конвертеров: переименовать картинки в i_NNN, записать
    главы, слить/записать манифест. В режиме append продолжает нумерацию slug'ов
    и i_NNN с того, что уже на диске. Возвращает (записано сейчас, всего)."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "images").mkdir(exist_ok=True)
    orphan_images = set(orphan_images or set())

    prev_manifest: dict = {}
    prev_rows: list[dict] = []
    if append and (out / "_manifest.json").exists():
        prev_manifest = json.loads((out / "_manifest.json").read_text("utf-8"))
        prev_rows = prev_manifest.get("chapters", [])

    # ── стабильные имена картинок i_NNN ──
    img_start = 0
    if append:
        img_start = max((int(m.group(1)) for f in (out / "images").glob("i_*")
                         if (m := re.match(r"i_(\d+)", f.name))), default=0)
    order = [im for c in chapters for im in c.illustrations] + sorted(orphan_images)
    rename: dict[str, str] = {}
    for name in dict.fromkeys(order):
        rename[name] = f"i_{img_start + len(rename) + 1:03d}{_img_ext(name)}"
    for name, data in images.items():
        (out / "images" / rename.get(name, name)).write_bytes(data)
    unresolved: set[str] = set()
    for c in chapters:
        c.illustrations = [rename.get(x, x) for x in c.illustrations]
        for m in re.findall(r"@@IMAGE:([^@]+)@@", c.body):
            if m in rename:
                c.body = c.body.replace(f"@@IMAGE:{m}@@", f"@@IMAGE:{rename[m]}@@")
            elif m not in images:
                unresolved.add(m)
    orphan_images = {rename.get(x, x) for x in orphan_images}

    # ── запись глав с продолжением per-kind счётчика ──
    seen: dict[str, int] = {}
    for r in prev_rows:
        seen[r["type"]] = seen.get(r["type"], 0) + 1
    slugs: list[str] = []
    for ch in chapters:
        idx = seen.get(ch.kind, 0)
        seen[ch.kind] = idx + 1
        slugs.append(write_chapter(out, ch, arc, nested=nested, index=idx))

    merged = prev_rows + manifest_rows(chapters, nested=nested, slugs=slugs)
    meta = {
        "arc": arc, "generator": generator,
        "source": (prev_manifest.get("source") or []) + list(sources),
        "orphan_images": sorted(set(prev_manifest.get("orphan_images") or []) | orphan_images),
        "images_total": img_start + len(rename),
    }
    if unresolved:
        meta["unresolved_image_refs"] = sorted(unresolved)
    meta.update(extra or {})
    write_manifest_rows(out, merged, meta)
    return len(chapters), len(merged)


# ─────────────────────────── отчёт ───────────────────────────

class Reporter:
    """Спойлер-безопасный отчёт: цифры всегда, названия только с show_titles."""

    def __init__(self, show_titles: bool = False):
        self.show_titles = show_titles

    def table(self, chapters: list[Chapter]) -> None:
        print(f"\n{'slug':>16}  {'тип':<10} {'фаза':>4} {'слов':>7} {'абз':>5}  илл")
        for i, c in enumerate(chapters):
            line = (f"{chapter_slug(c, i):>16}  {c.kind:<10} "
                    f"{(c.phase or ''):>4} {c.words:>7} {c.n_paragraphs:>5}  "
                    f"{len(c.illustrations)}")
            if self.show_titles and c.title:
                line += f"   — {c.title}"
            print(line)

    def summary(self, chapters: list[Chapter], report: dict, *, binaries: int = 0,
               inline_units: list[Chapter] | None = None) -> None:
        kinds: dict[str, int] = {}
        for c in chapters:
            kinds[c.kind] = kinds.get(c.kind, 0) + 1
        print("\n" + "─" * 60)
        print("итого по типам: " + ", ".join(f"{k}×{v}" for k, v in sorted(kinds.items())))
        print(f"глав (сквозная нумерация): {report['chapters']}")
        print(f"всего слов: {sum(c.words for c in chapters):,}")
        inline = sum(len(c.illustrations) for c in (inline_units or chapters))
        if binaries:
            print(f"иллюстраций привязано к тексту: {inline} из {binaries}")
        if report["nonstandard"]:
            print(f"нестандартные номера: {report['nonstandard']}")
        if report["dup_labels"]:
            print(f"! дубли номеров (label, unit#, unit#): {report['dup_labels']}")
        if report["gap_labels"]:
            print(f"! пропущенные номера в источнике: {report['gap_labels']}")
        if report["shift_suspected"]:
            print("! дубль + пропуск => СДВИГ нумерации в источнике, "
                  "не потерянная глава (number проставлен счётчиком, ссылки целы)")
        cw = [c.words for c in chapters if c.kind == "chapter"]
        if cw:
            med = sorted(cw)[len(cw) // 2]
            tiny = [c.label or c.number or i for i, c in enumerate(chapters)
                    if c.kind == "chapter" and c.words < max(300, med * 0.25)]
            huge = [c.label or c.number or i for i, c in enumerate(chapters)
                    if c.kind == "chapter" and med and c.words > med * 3]
            if tiny:
                print(f"! подозрительно короткие главы (проверь разбиение): {tiny}")
            if huge:
                print(f"! подозрительно длинные главы (возможно слиты): {huge}")


def arc_folder(key: str) -> str:
    """'7' → 'arc-07', '4.5' → 'arc-04-5' (совпадает с конвенцией имён ассетов ТЗ §6.1)."""
    key = str(key)
    if "." in key:
        a, b = key.split(".", 1)
        return f"arc-{a.zfill(2)}-{b}"
    return f"arc-{key.zfill(2)}"


def compress_ranges(nums: Iterable[int]) -> str:
    out: list[list[int]] = []
    for x in sorted(set(nums)):
        if out and x == out[-1][1] + 1:
            out[-1][1] = x
        else:
            out.append([x, x])
    return ", ".join(f"{a}\u2013{b}" if a != b else str(a) for a, b in out)

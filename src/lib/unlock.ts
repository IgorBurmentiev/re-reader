// Разблокировка «Дополнительного» — считается на клиенте (прогресс чтения
// живёт только в localStorage).
//
// Тома 1–9 (ранобэ, арки 1–3) — сравнение точное: том сборника побочных
// совпадает с настоящим номером тома книги, проверяем напрямую по полю
// `volume` у глав.
//
// Тома 10–45 (веб-новелла, арки 4–10) — точная таблица «том → номер
// последней главы арки, вошедшей в этот том» (TOM_MAX_CHAPTER), сверено
// пользователем по официальным сайтам (не по нашему переводу — названия глав
// там могут отличаться, но конец тома — это конец тома независимо от них).
// Где в томе последняя единица — интерлюдия, а не глава (Том 12, 36, 45),
// взят номер главы, ПОСЛЕ которой она стоит по data/arcs.md.
// Тома 31–33 арки 7 в таблице неточные — сверки по сайтам не было, взяты по
// аналогии по фазам (данные по остальным томам арки 7 плюс arcs.md).
//
// «Танпэнсю» (сборники самих побочных историй, не тома основной серии) и
// тома за пределами таблицы (46+, онгоинг арки 10) — точных данных нет,
// используется прежнее приближение: номер контейнера пропорционально
// проецируется на номер фазы арки.
const TOM_MAX_CHAPTER: Record<number, number> = {
  10: 23, 11: 51, 12: 79, 13: 97, 14: 117, 15: 136,       // арка 4 (136 — конец арки)
  16: 19, 17: 36, 18: 48, 19: 60, 20: 81,                  // арка 5 (81 — конец арки)
  21: 18, 22: 33, 23: 54, 24: 70, 25: 90,                  // арка 6 (90 — конец арки)
  26: 12, 27: 24, 28: 40, 29: 54, 30: 60, 31: 75, 32: 96, 33: 110, // арка 7 (110 — конец арки)
  34: 15, 35: 28, 36: 43, 37: 60, 38: 74,                  // арка 8 (74 — конец арки)
  39: 13, 40: 23, 41: 36, 42: 49, 43: 59,                  // арка 9 (59 — конец арки)
  44: 12, 45: 24,                                          // арка 10 (онгоинг, дальше не задано)
};

// глава/часть считается прочитанной только при ровно 100% (см. reader.ts)
export const READ_DONE = 1;

export interface ChapterMeta {
  arc: string;
  number?: string;
  volume?: number;
}
export interface ArcUnlockMeta {
  structure: "ln" | "wn";
  volumes: string; // "10–15"
  phases: { n: number; ranges: [number, number][] }[];
}
export interface UnlockItem {
  slug: string;
  read_after: { arc: number; container: string | null } | null;
}

export function computeUnlocked(
  progress: Record<string, number>,
  chapterMeta: Record<string, ChapterMeta>,
  arcsMeta: Record<string, ArcUnlockMeta>,
  items: UnlockItem[],
): Set<string> {
  const maxNumByArc: Record<string, number> = {};
  const maxVolByArc: Record<string, number> = {};
  for (const [id, pct] of Object.entries(progress)) {
    if (pct < READ_DONE) continue;
    const m = chapterMeta[id];
    if (!m) continue;
    if (m.number != null && !Number.isNaN(+m.number)) {
      maxNumByArc[m.arc] = Math.max(maxNumByArc[m.arc] ?? 0, +m.number);
    }
    if (m.volume != null) maxVolByArc[m.arc] = Math.max(maxVolByArc[m.arc] ?? 0, m.volume);
  }

  const unlocked = new Set<string>();
  for (const item of items) {
    if (!item.read_after) {
      // спешлы / твиттер / IF и т.п. без привязки к арке — по задумке всё
      // должно начинаться закрытым; точные правила для этих категорий ещё
      // не заданы, поэтому пока не открываем вообще (не добавляем в unlocked)
      continue;
    }
    const arcKey = String(item.read_after.arc);
    const meta = arcsMeta[arcKey];
    if (!meta) continue; // арка не найдена — не открываем на всякий случай

    const contLabel = item.read_after.container ?? "";
    const contNum = contLabel.match(/\d+/)?.[0];
    const isTom = /^Том/i.test(contLabel);

    if (meta.structure === "ln") {
      const reached = maxVolByArc[arcKey] ?? 0;
      if (!contNum || reached >= +contNum) unlocked.add(item.slug);
      continue;
    }

    if (isTom && contNum && TOM_MAX_CHAPTER[+contNum] != null) {
      if ((maxNumByArc[arcKey] ?? 0) >= TOM_MAX_CHAPTER[+contNum]) unlocked.add(item.slug);
      continue;
    }

    // приближение (Танпэнсю / том вне таблицы): номер контейнера
    // пропорционально проецируется на номер фазы арки
    if (!meta.phases.length) continue;
    const range = meta.volumes.match(/(\d+)\D+(\d+)/);
    // арка ещё идёт (напр. "44–…") — второго числа нет; тогда проецировать
    // не на что, требуем прочтения всего, что вообще вышло по арке на сейчас
    const single = !range && meta.volumes.match(/(\d+)/);
    if (!range && !single) continue;
    const v0 = range ? +range[1] : +(single as RegExpMatchArray)[1];
    const v1 = range ? +range[2] : v0;
    const totalVols = Math.max(1, v1 - v0 + 1);
    const idx = contNum ? Math.min(totalVols - 1, Math.max(0, +contNum - v0)) : 0;
    const targetPhase = Math.min(
      meta.phases.length,
      Math.max(1, Math.ceil(((idx + 1) / totalVols) * meta.phases.length)),
    );
    const ph = meta.phases.find((p) => p.n === targetPhase);
    const maxChNum = ph ? Math.max(...ph.ranges.map((r) => r[1])) : 0;
    if ((maxNumByArc[arcKey] ?? 0) >= maxChNum) unlocked.add(item.slug);
  }
  return unlocked;
}

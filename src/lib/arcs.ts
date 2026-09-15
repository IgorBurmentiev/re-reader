import arcsData from "../../data/arcs.json";

export interface Phase {
  n: number;
  ranges: [number, number][];
}
export interface ArcMeta {
  arc: string;
  slug: string;
  title: string;
  aka?: string[];
  theme: string;
  theme_light: string;
  volumes: string;
  structure: "ln" | "wn";
  status?: string;
  expected_total?: number | null;
  expected_chapters?: number;
  nonstandard?: string[];
  phases?: Phase[];
}

export const ARCS = arcsData as ArcMeta[];

export const arcBySlug = (slug: string): ArcMeta | undefined =>
  ARCS.find((a) => a.slug === slug);

// Японское название арки целиком — для заставок (декоративная надпись).
// romaji и русский смысл — в комментарии, чтобы легко сверить/поправить.
// Сверено по вики/твиттеру фанатов вебки (2026-09) — часть арок здесь
// сознательно даны по названию манга-адаптации, а не «сырому» вебки:
//  1, 2, 4 — названия манги (王都の一日/屋敷の一週間/聖域と強欲の魔女);
//            у вебки официально 怒涛の一日目/激動の一週間/永遠の契約
//  6 — устоявшееся фанатское прозвище арки (プレアデス監視塔), у вебки
//      официально 記憶の回廊
//  7 — расширенное описание (важны обе половины арки — Отбор и Волчья
//      страна), у вебки официально только 狼の国
// Арка 3 (было 王都動乱 — не нашлось нигде, похоже опечатка/ошибка) и арка 5
// (было 歴史を紡ぐ星々 — на один иероглиф отличалось от настоящего названия)
// поправлены на точные официальные.
export const ARC_JP: Record<string, { jp: string; romaji: string }> = {
  "1": { jp: "王都の一日", romaji: "Ōto no Ichinichi" }, //  день в столице (манга-тайтл)
  "2": { jp: "屋敷の一週間", romaji: "Yashiki no Isshūkan" }, //  неделя в особняке (манга-тайтл)
  "3": { jp: "再来の王都", romaji: "Sairai no Ōto" }, //  Возвращение в столицу
  "4": { jp: "聖域と強欲の魔女", romaji: "Seiiki to Gōyoku no Majo" }, //  Святилище и Ведьма Алчности (манга-тайтл)
  "5": { jp: "歴史を刻む星々", romaji: "Rekishi o Kizamu Hoshiboshi" }, //  звёзды, что творят историю
  "6": { jp: "プレアデス監視塔", romaji: "Pleiades Kanshitō" }, //  Дозорная башня Плеяд (фанатское прозвище)
  "7": { jp: "選帝の儀と狼の国", romaji: "Sentei no Gi to Ōkami no Kuni" }, //  Отбор императора / Страна волков
  "8": { jp: "ヴィンセント・ヴォラキア", romaji: "Vincent Vollachia" },
  "9": { jp: "名も無き星の光", romaji: "Na mo Naki Hoshi no Hikari" }, //  Свет безымянной звезды
  "10": { jp: "獅子王の国", romaji: "Shishiō no Kuni" }, //  Страна Короля-льва
};

/** обратная совместимость: короткий иероглиф, если где-то ещё нужен */
export const ARC_KANJI: Record<string, string> = {
  "1": "都", "2": "館", "3": "都", "4": "契", "5": "星",
  "6": "塔", "7": "狼", "8": "帝", "9": "光", "10": "獅",
};

/** фаза для номера главы по диапазонам из arcs.json */
export function phaseOf(arc: ArcMeta, n: number): number | undefined {
  for (const p of arc.phases ?? []) {
    for (const [a, b] of p.ranges) if (n >= a && n <= b) return p.n;
  }
  return undefined;
}

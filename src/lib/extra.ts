import registryData from "../../content/extra/_index.json";

export interface ExtraEntry {
  slug: string;
  title: string;
  title_jp?: string;
  category: string;
  tags: string[];
  translator?: string;
  fanart?: string;
  parts: number;
  part_slugs: string[];
  read_after: { arc: number; container: string | null } | null;
  status: "ok" | "no_translation" | "partial" | "soon";
  words: number;
  // необязательная визуальная подгруппа внутри категории — истории с общим
  // составом персонажей, но без сквозного сюжета/подменю (см. src/pages/extra.astro);
  // ничего не меняет в разблокировке/статусах, только группирует карточки рядом
  subgroup?: string;
}

export const REGISTRY = registryData as ExtraEntry[];

// порядок и подписи разделов — Ex/IF отдельно и первыми (как книги/особый формат),
// дальше побочные по аркам одним общим блоком, потом мелкие категории
export const CATEGORY_ORDER = [
  "ex", "if", "side", "comic_alive", "birthday_emilia", "birthday_remram",
  "event", "twitter",
] as const;

export const CATEGORY_LABEL: Record<string, string> = {
  ex: "Ex-издания",
  if: "IF-истории",
  side: "Побочные истории",
  comic_alive: "Comic Alive",
  birthday_emilia: "День рождения Эмилии",
  birthday_remram: "День рождения Рем и Рам",
  event: "Ивентовые спешлы",
  twitter: "Истории из твиттера",
};

// короткий бейдж на строке — то же самое, но компактнее
export const CATEGORY_TAG: Record<string, string> = {
  ex: "Ex",
  if: "IF",
  side: "Побочная",
  comic_alive: "Comic Alive",
  birthday_emilia: "День рождения",
  birthday_remram: "День рождения",
  event: "Спешл",
  twitter: "Твиттер",
};

export const STATUS_LABEL: Record<ExtraEntry["status"], string> = {
  ok: "",
  no_translation: "нет перевода",
  partial: "неполный перевод",
  soon: "скоро",
};

/** сортировка «очереди закрытых»: по арке, потом по номеру тома/танпэнсю
 *  в контейнере (если есть) — чем раньше, тем выше */
export function unlockSortKey(e: ExtraEntry): [number, number] {
  if (!e.read_after) return [999, 0];
  const n = e.read_after.container?.match(/\d+/)?.[0];
  return [e.read_after.arc, n ? parseInt(n, 10) : 0];
}

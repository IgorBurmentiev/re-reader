import type { ImageMetadata } from "astro";

// Обложки лежат в /assets/covers/ (вне src, добавляются вручную — ТЗ §6.1).
// Пропорции у файлов разные (от 0.56 до 2.8) — компоненты Hero/Cover это терпят.
const heroes = import.meta.glob<{ default: ImageMetadata }>(
  "/assets/covers/arcs/*-hero.{jpg,jpeg,png,webp,avif}",
  { eager: true },
);
const cards = import.meta.glob<{ default: ImageMetadata }>(
  "/assets/covers/arcs/*-card.{jpg,jpeg,png,webp,avif}",
  { eager: true },
);
const site = import.meta.glob<{ default: ImageMetadata }>(
  "/assets/covers/site-hero.{jpg,jpeg,png,webp,avif}",
  { eager: true },
);

const pick = (
  map: Record<string, { default: ImageMetadata }>,
  needle: string,
): ImageMetadata | undefined => {
  const key = Object.keys(map).find((k) => k.includes(needle));
  return key ? map[key].default : undefined;
};

/** slug вида "arc-07"; для арки 4.5 обложки нет (edge case) */
export const heroFor = (slug: string) => pick(heroes, `/${slug}-hero`);
export const cardFor = (slug: string) => pick(cards, `/${slug}-card`);
export const siteHero = (): ImageMetadata | undefined =>
  Object.values(site)[0]?.default;

// Точка фокуса hero-баннера — по умолчанию центр, годится почти всем
// горизонтальным артам. Портретные арты (во весь рост или крупный план)
// от широкого баннера обрезаются сверху/снизу «по центру» и часто теряют
// голову персонажа — для них здесь задаётся ручной сдвиг вверх.
const HERO_FOCUS: Record<string, string> = {
  "mechta-korolya-lva": "50% 6%",
  "hroniki-bezuprechnogo": "50% 25%",
  "mimagau-if": "50% 10%",
  "bratstvo-pleyad": "50% 15%",
  "dnevnik-vypolneniya-obeschanij-yuliusa-yukliusa-1": "50% 28%",
  "elegantnyj-urok": "50% 15%",
  "elza-i-mejli-dnevnik-sester-ubijc-ubijstvo-1": "50% 15%",
  "dni-gornichnyh-frederiki-i-petry-1": "50% 25%",
  "korolevstvo-drakona-zametki-mejli-o-zverodemonah-1": "50% 30%",
  "korolevstvo-drakona-zametki-mejli-o-zverodemonah-3": "50% 30%",
  "lyubov-k-ushedshim-dnyam": "50% 5%",
  "naciya-drakona-hroniki-poiska-propavshego-rebenka-1": "50% 30%",
  "odnazhdy-v-lugunike-ii": "50% 15%",
  "pervaya-missiya": "50% 5%",
  "sestry-oni-iz-skrytoj-derevni": "50% 40%",
  "zemlya-volkov-smert-slabym-poschady-ne-budet-1": "50% 5%",
  "zemlya-volkov-smert-slabym-poschady-ne-budet-9": "50% 40%",
  "zemlya-vozrozhdayuschihsya-volkov-velichie-vydayuschegosya-i": "50% 5%",
  "skazanie-ob-aloj-princesse": "50% 0%",
  "azamuku-if": "50% 0%",
  "ayamacu-if-gordynya": "50% 0%",
  "re-if-nacuki-rem-len-blyu-rej-tom": "50% 0%",
  "sasageru-if": "50% 0%",
  "cugihagu-if-chrevougodie": "50% 0%",
  "afera-v-lugunike": "50% 0%",
  "vedmy-posle-chaepitiya-odna-bezumnaya-noch": "50% 0%",
  "istoriya-o-poltergejste": "50% 0%",
  "korolevskij-otbor-pervyj-kontakt": "50% 0%",
  "suschnost-mecha": "50% 0%",
  "uzy-lda-before-memories": "50% 0%",
};
export const heroFocus = (slug: string): string => HERO_FOCUS[slug] ?? "50% 50%";

// Увеличение hero-арта поверх обычного cover-кропа — для тех случаев, где
// сюжетный центр композиции (не портрет, а разлапистая широкая сцена) теряется
// в узкой полосе баннера и «не умещается» ни при каком сдвиге фокуса.
const HERO_ZOOM: Record<string, number> = {
  "zhurnal-rekonstrukcii-pristelly-1": 1.2,
};
export const heroZoom = (slug: string): number => HERO_ZOOM[slug] ?? 1;

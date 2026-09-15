// 30 шрифтов в 5 группах, отбор под кириллицу (ТЗ §5).
// Google Fonts CDN. Локальный Fontsource (offline) — оставлен на потом,
// это единственная незакрытая оптимизация UI.
export const GFONTS_HREF =
  "https://fonts.googleapis.com/css2?" +
  [
    "family=EB+Garamond:ital,wght@0,400;0,500;1,400",
    "family=Literata:ital,opsz@0,7..72;1,7..72",
    "family=Forum",
    "family=Podkova:wght@400;500",
    "family=Bitter:ital@0;1",
    "family=Kelly+Slab",
    "family=Golos+Text:wght@400;500;600",
    "family=Cuprum:ital@0;1",
    "family=Jura",
    "family=Philosopher:ital@0;1",
    "family=Tenor+Sans",
    "family=Yeseva+One",
    "family=Ruslan+Display",
    "family=Underdog",
    "family=Bad+Script",
    "family=Marck+Script",
    "family=Neucha",
    "family=Pacifico",
    "family=Press+Start+2P",
    "family=Amatic+SC:wght@400;700",
    "family=Flow+Circular",
    "family=Rubik+Doodle+Shadow",
    "family=Rubik+Glitch",
    "family=Kablammo",
    "family=Montserrat+Underline",
    "family=Tiny5",
  ].join("&") +
  "&display=swap";

// [подпись, css-стек, group]
export type FontEntry = [label: string, stack: string];
export const FONT_GROUPS: [string, FontEntry[]][] = [
  ["С засечками", [
    ["Garamond", "'EB Garamond', serif"],
    ["Literata", "'Literata', serif"],
    ["Forum", "'Forum', serif"],
    ["Podkova", "'Podkova', serif"],
    ["Bitter", "'Bitter', serif"],
    ["Kelly Slab", "'Kelly Slab', serif"],
  ]],
  ["Без засечек", [
    ["Golos", "'Golos Text', sans-serif"],
    ["Cuprum", "'Cuprum', sans-serif"],
    ["Jura", "'Jura', sans-serif"],
    ["Philosopher", "'Philosopher', sans-serif"],
    ["Tenor Sans", "'Tenor Sans', sans-serif"],
    ["Verdana", "Verdana, sans-serif"],
  ]],
  ["Заголовочные", [
    ["Yeseva One", "'Yeseva One', serif"],
    ["Ruslan Display", "'Ruslan Display', serif"],
    ["Underdog", "'Underdog', serif"],
  ]],
  ["Рукописные", [
    ["Bad Script", "'Bad Script', cursive"],
    ["Marck Script", "'Marck Script', cursive"],
    ["Neucha", "'Neucha', cursive"],
    ["Pacifico", "'Pacifico', cursive"],
    ["Ink Free", "'InkFreeLocal', cursive"],
    ["Segoe Script", "'SegoeScriptLocal', cursive"],
    ["Mistral", "'MistralLocal', cursive"],
  ]],
  ["Ради веселья", [
    ["Press Start 2P", "'Press Start 2P', monospace"],
    ["Tiny5", "'Tiny5', monospace"],
    ["Amatic SC", "'Amatic SC', cursive"],
    ["Montserrat Underline", "'Montserrat Underline', sans-serif"],
    ["Rubik Glitch", "'Rubik Glitch', cursive"],
    ["Rubik Doodle Shadow", "'Rubik Doodle Shadow', cursive"],
    ["Kablammo", "'Kablammo', cursive"],
    ["Flow Circular", "'Flow Circular', cursive"],
  ]],
];

export const DEFAULT_FONT = "'EB Garamond', serif";
export const DEFAULT_FONT2 = "'Bad Script', cursive";

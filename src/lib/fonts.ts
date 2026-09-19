// 30 шрифтов в 5 группах, отбор под кириллицу (ТЗ §5).
// Шрифты раздаются с самого сайта (public/fonts, см. scripts/fetch-fonts.mjs) —
// не с серверов Google: так они лежат в офлайн-кэше и работают без интернета.
// Чтобы добавить шрифт: допишите семейство в FAMILIES в scripts/fetch-fonts.mjs,
// запустите `node scripts/fetch-fonts.mjs` и добавьте строку в FONT_GROUPS ниже.

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

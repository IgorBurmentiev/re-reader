// 20 тем: 10 тёмных + 10 светлых, парами по оттенку (ТЗ §6).
// Ключи совпадают с полем `theme` в data/arcs.json.
export interface Theme {
  n: string; // название
  m: "dark" | "light";
  p: string; // --paper
  p2: string; // --paper-2
  i: string; // --ink
  d: string; // --ink-dim
  g: string; // --gold (акцент)
  gs: string; // --gold-soft
}

export const THEMES: Record<string, Theme> = {
  midnight: { n: "Полночь", m: "dark", p: "#0b0e18", p2: "#111524", i: "#d9d6cd", d: "#8d8a84", g: "#c9a227", gs: "#e0c56a" },
  nocturne: { n: "Ночник", m: "dark", p: "#15100c", p2: "#1d1611", i: "#dbc9a8", d: "#94836a", g: "#c98f27", gs: "#e3b65f" },
  conifer: { n: "Хвойный", m: "dark", p: "#0a1410", p2: "#102019", i: "#d4ded3", d: "#86968a", g: "#6fbf8f", gs: "#9ad9b3" },
  sakura: { n: "Сакура", m: "dark", p: "#150e14", p2: "#1e1520", i: "#e8d7de", d: "#9a8792", g: "#e08aa6", gs: "#f2b3c7" },
  lagoon: { n: "Бирюза", m: "dark", p: "#08131a", p2: "#0e1e28", i: "#d2e2e6", d: "#7f979e", g: "#4fc3d9", gs: "#8fdcea" },
  amethyst: { n: "Аметист", m: "dark", p: "#120e1c", p2: "#1a1428", i: "#ded7ea", d: "#918aa5", g: "#a487e0", gs: "#c4b0f0" },
  ember: { n: "Багрянец", m: "dark", p: "#150b0c", p2: "#1f1113", i: "#e6d5d2", d: "#9c8683", g: "#d2686a", gs: "#e89496" },
  ash: { n: "Пепел", m: "dark", p: "#111315", p2: "#1a1d20", i: "#dcdedf", d: "#8a9195", g: "#9fb4c2", gs: "#c2d2dc" },
  frost: { n: "Иней", m: "dark", p: "#0c1117", p2: "#141b23", i: "#d7e0e8", d: "#87949f", g: "#8fb6d9", gs: "#b6d4ef" },
  wormwood: { n: "Полынь", m: "dark", p: "#101207", p2: "#191c0e", i: "#dcdcc4", d: "#8f9276", g: "#b5c94f", gs: "#d0e07a" },

  parchment: { n: "Пергамент", m: "light", p: "#f5f1e8", p2: "#fffdf7", i: "#22201c", d: "#6d675c", g: "#8a6d1f", gs: "#6f5717" },
  sepia: { n: "Сепия", m: "light", p: "#ece0c8", p2: "#f6ecd8", i: "#3a2f21", d: "#7a6a52", g: "#8f6b23", gs: "#75551a" },
  mint: { n: "Мята", m: "light", p: "#edf4ee", p2: "#f8fbf7", i: "#1f2b23", d: "#5f7166", g: "#2f7d55", gs: "#24623f" },
  blush: { n: "Румянец", m: "light", p: "#fbf0f3", p2: "#fffafb", i: "#2d1f26", d: "#7b6470", g: "#b8406b", gs: "#983055" },
  shore: { n: "Лагуна", m: "light", p: "#eaf3f5", p2: "#f7fcfd", i: "#16262c", d: "#5a747c", g: "#16788f", gs: "#0f5f73" },
  lavender: { n: "Лаванда", m: "light", p: "#f2eff9", p2: "#fbf9ff", i: "#241d33", d: "#6b6284", g: "#6a4bb0", gs: "#553a92" },
  dawn: { n: "Заря", m: "light", p: "#fdefec", p2: "#fffaf8", i: "#2e1c18", d: "#7d635c", g: "#b8483c", gs: "#98372d" },
  mist: { n: "Туман", m: "light", p: "#f0f1f2", p2: "#fafbfc", i: "#1e2225", d: "#6a7175", g: "#46606f", gs: "#334b58" },
  crust: { n: "Наст", m: "light", p: "#eef2f7", p2: "#fbfcfe", i: "#1b2530", d: "#5f6f7d", g: "#3f6ea8", gs: "#2f5688" },
  meadow: { n: "Луг", m: "light", p: "#f3f2e2", p2: "#fbfbf1", i: "#262a16", d: "#6a704f", g: "#5f7326", gs: "#4b5c1b" },
};

// пары день/ночь для переключателя (перекидывает на парную, не на дефолт)
export const PAIR: Record<string, string> = {
  midnight: "parchment", nocturne: "sepia", conifer: "mint", sakura: "blush",
  lagoon: "shore", amethyst: "lavender", ember: "dawn", ash: "mist",
  frost: "crust", wormwood: "meadow",
};
for (const [d, l] of Object.entries({ ...PAIR })) PAIR[l] = d;

export const DEFAULT_THEME = "midnight";

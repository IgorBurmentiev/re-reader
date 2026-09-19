// Разовый скрипт (не часть сборки): скачивает шрифты из Google Fonts в
// public/fonts/ и пишет public/fonts/fonts.css с локальными @font-face —
// чтобы шрифты раздавались с самого сайта и лежали в офлайн-кэше, а не
// зависели от серверов Google. Список семейств — FAMILIES ниже
// (тот же набор, что и в src/lib/fonts.ts); при добавлении шрифта допишите
// его сюда и перезапустите:
//   node scripts/fetch-fonts.mjs
// Оставляем только нужные подмножества символов (кириллица + латиница).

import { writeFileSync, mkdirSync, rmSync, existsSync } from "node:fs";
import { createHash } from "node:crypto";

const FAMILIES = [
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
];

const KEEP = new Set(["cyrillic", "cyrillic-ext", "latin", "latin-ext"]);
const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36";

async function get(url, opts = {}) {
  for (let i = 1; ; i++) {
    try {
      const r = await fetch(url, { ...opts, signal: AbortSignal.timeout(30000) });
      if (r.ok) return r;
      throw new Error("HTTP " + r.status);
    } catch (e) {
      if (i >= 8) throw e;
    }
  }
}

const families = FAMILIES;
const cssUrl = "https://fonts.googleapis.com/css2?" + families.join("&") + "&display=swap";

const css = await (await get(cssUrl, { headers: { "User-Agent": UA } })).text();

const OUT = "public/fonts";
if (existsSync(OUT)) rmSync(OUT, { recursive: true });
mkdirSync(OUT, { recursive: true });

const files = new Map(); // remote url -> local name
let outCss = "/* СГЕНЕРИРОВАНО scripts/fetch-fonts.mjs — не редактировать вручную. */\n";
let bytes = 0;

for (const m of css.matchAll(/\/\* ([a-z-]+) \*\/\s*(@font-face\s*\{[^}]*\})/g)) {
  const [, subset, block] = m;
  if (!KEEP.has(subset)) continue;
  const remote = block.match(/url\((https:[^)]+\.woff2)\)/)[1];
  let local = files.get(remote);
  if (!local) {
    const buf = Buffer.from(await (await get(remote)).arrayBuffer());
    local = createHash("sha1").update(remote).digest("hex").slice(0, 10) + ".woff2";
    writeFileSync(`${OUT}/${local}`, buf);
    files.set(remote, local);
    bytes += buf.length;
  }
  outCss += `/* ${subset} */\n` + block.replace(remote, `/fonts/${local}`) + "\n";
}

writeFileSync(`${OUT}/fonts.css`, outCss);
console.log(`шрифтов-файлов: ${files.size}, всего ${(bytes / 1024 / 1024).toFixed(2)} МБ`);

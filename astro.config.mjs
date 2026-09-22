// @ts-check
import { defineConfig } from "astro/config";
import remarkGfm from "remark-gfm";

// Личная читалка Re:Zero. Без индексации, без внешних сервисов.
// Контент — Markdown в /content, собирается статикой (см. ТЗ §2).
export default defineConfig({
  site: "https://rezero.local",
  trailingSlash: "ignore",
  build: { format: "directory" },
  markdown: {
    smartypants: false, // типографику уже сделали конвертеры
    // gfm:false + свой remarkGfm — чтобы передать singleTilde:false. По
    // умолчанию GFM считает зачёркиванием даже ОДНУ тильду (~текст~), а не
    // только двойную (~~текст~~) — а переводчики повсеместно используют
    // одиночную тильду как авторский приём (растянутая/певучая речь
    // персонажа, "да~а"), никак не связанный с зачёркиванием. Из-за этого
    // в тексте возникали случайные зачёркнутые куски, иногда всего в одну
    // букву, если рядом в реплике было две тильды подряд. Сноски, таблицы,
    // автоссылки, чек-листы — весь остальной GFM — это тот же remark-gfm,
    // ничего из этого не отключается, меняется только этот один параметр.
    gfm: false,
    remarkPlugins: [[remarkGfm, { singleTilde: false }]],
    shikiConfig: { theme: "css-variables" },
  },
  devToolbar: { enabled: false },
});

// @ts-check
import { defineConfig } from "astro/config";

// Личная читалка Re:Zero. Без индексации, без внешних сервисов.
// Контент — Markdown в /content, собирается статикой (см. ТЗ §2).
export default defineConfig({
  site: "https://rezero.local",
  trailingSlash: "ignore",
  build: { format: "directory" },
  markdown: {
    smartypants: false, // типографику уже сделали конвертеры
    shikiConfig: { theme: "css-variables" },
  },
  devToolbar: { enabled: false },
});

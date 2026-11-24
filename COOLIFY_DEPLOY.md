# PrintHub — Coolify (VPS) ga Joylashtirish Qo'llanmasi

Ushbu loyiha **Web sayt (FastAPI)** va **Telegram Bot (aiogram 3)** ni bitta Docker Compose to'plamida ishga tushiradi. Ikkalasi bitta umumiy `printhub_data` xotirasini (`/app/data`) ishlatadi, shuning uchun `gears.json`, Sela shablonlari va natijalar doim sinxron bo'ladi.

## 1. Git repozitoriyga yuklash
`print_hub/` papkasini GitHub / GitLab repozitoriyga push qiling.

> **Eslatma (`OCR-B` shrifti):** Linux Docker ichida `LiberationSans` va `LiberationMono` avtomatik o'rnatiladi. Agar Sela barkod raqamlari aynan `OCR-B 10 BT.ttf` va `arial.ttf` bilan chiqishini istasangiz, ushbu `.ttf` fayllarni `print_hub/data/fonts/` papkasiga tashlab qo'ying.

## 2. Coolify da sozlash
1. Coolify panelida **New Resource → Public/Private Git Repository** ni tanlang.
2. Build Pack sifatida **Docker Compose** ni tanlang (`docker-compose.yml` avtomatik topiladi).
3. `web` servisi uchun domeningizni biriktiring (masalan: `https://print.yourdomain.com`, port `8000`).
4. **Environment Variables** bo'limiga quyidagilarni kiriting:
   - `WEB_PASSWORD` — Web saytga kirish uchun PIN/parol (masalan: `2026`)
   - `SECRET_KEY` — istalgan uzun tasodifiy satr
   - `TELEGRAM_BOT_TOKEN` — `@BotFather` dan olingan token
   - `ALLOWED_TELEGRAM_IDS` — ruxsat berilgan Telegram ID lar (vergul bilan: `123456789,987654321`)
   - `PUBLIC_URL` — `https://print.yourdomain.com` (Telegram botda Web App tugmasi chiqishi uchun)
5. **Deploy** tugmasini bosing.

## 3. Birinchi marta ishga tushirgandan keyin
1. Web saytni oching (`https://print.yourdomain.com`) va parol bilan kiring.
2. **Sela Etiketka** bo'limida `⬆️ Yangi shablon yuklash` tugmasi orqali Sela `.pdf` yoki `.svg` shabloningizni bir marta yuklab qo'ying — u doimiy volume da saqlanadi va Web hamda Telegram Bot uchun ishlaydi.
3. **Vallar (Gears)** bo'limida o'zingizdagi mavjud vallarni tekshirib qo'ying.

## 4. Claude Code + VectorCraft MCP va Web Muharriri
Docker konteyner ([Dockerfile](Dockerfile)) ichiga avtomatik ravishda quyidagilar o'rnatiladi:
- **Claude Code CLI (`@anthropic-ai/claude-code`)** — sizning Claude Pro/Max obunangiz bilan ishlaydi.
- **`vectorcraft-cli` (v0.24.1)** — Headless VectorCraft MCP serveri (`vectorcraft-cli mcp --headless`) va `.vectorcraft` ↔ `.pdf` konverteri.
- **`vectorcraft-web` (v0.24.1 WASM)** — Brauzer ichida (`/vectorcraft/` va **VectorCraft Web** menyusida) to'liq ishlovchi grafik muharrir.

### Claude Obunasini Ulash (2 xil usul):
1. **Web-dastur ichidan:** **AI Dizayn & Skills → Skills, Fayllar & Claude Login** bo'limiga kiring:
   - **A-usul:** **"Claude Login Havolasini Olish"** tugmasini bosib, chiqqan OAuth havola orqali akkauntingizga kiring va tasdiqlash kodini kiriting.
   - **B-usul:** Kompyuteringizda `claude setup-token` orqali olingan tokenni (`CLAUDE_CODE_OAUTH_TOKEN`) formaga (yoki Coolify Environment Variables ga) kiriting.
2. Login ma'lumotlari `/app/data/claude_home` ichida, maxsus Skillar `/app/data/claude_workspace/.claude/skills/` ichida va doimiy dizayn fayllari `/app/data/claude_workspace/assets/` ichida saqlanadi (redeploy qilinganda o'chib ketmaydi).

## 5. Lokal kompyuterda sinash
```bash
pip install -r requirements.txt
uvicorn app.api:app --reload --port 8000
```
Brauzerda `http://localhost:8000` ni oching.

# Frontend (Next.js + TypeScript)

Монорепо на pnpm + Turborepo: три приложения и общие пакеты. Данные берутся **только** из API бэкенда; бизнес-логики во фронтенде нет.

| Папка | Что это | Адрес |
|---|---|---|
| `apps/web` | Сайт покупателя | http://localhost (dev: http://localhost:3000) |
| `apps/seller` | Панель продавца | /seller (dev: http://localhost:3001/seller) |
| `apps/admin` | Админка, поддержка, тех. операции | /admin (dev: http://localhost:3002/admin) |
| `packages/ui` | Дизайн-система: токены (forest-800 `#124929`), Tailwind preset, компоненты, карточка ошибки | — |
| `packages/i18n` | Тексты интерфейса uz / ru / en | — |
| `packages/api-client` | Клиент API: шлёт `X-Request-Id`, превращает ошибки в `ApiError` с `module`, `code`, `requestId` | — |

## Запуск для разработки

```bash
corepack enable
pnpm install
pnpm dev          # все три приложения; API ожидается на http://localhost:8000
```

`/api/*` и `/health/*` проксируются на бэкенд (переменная `INTERNAL_API_URL`).

## Проверки (то же, что в CI)

```bash
pnpm lint && pnpm typecheck && pnpm test && pnpm build
```

## Правила

- Любой текст интерфейса — ключ в `packages/i18n/src/locales/*.json` во всех трёх языках (тест проверяет, что ключи совпадают).
- Цвета, шрифты и радиусы — только из `packages/ui` (Tailwind-классы `bg-primary`, `text-ink-muted`, `forest-*`…), без «магических» hex в приложениях.
- Ошибки API показываются через `ErrorNotice`: пользователь видит код, модуль и ID запроса и может скопировать их одной кнопкой.

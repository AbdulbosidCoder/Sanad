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
- Цвета — только семантические классы из `packages/ui` (`bg-surface`, `text-ink`, `bg-primary`, `text-ink-muted`, `bg-hero`, `bg-nav`…), без hex и без `forest-*` в интерфейсе. Тогда экран сам работает в дневной и ночной теме.
- Темы: дневная, ночная и «как в системе». Значения — в `packages/ui/src/tokens.ts` (`themes.light`, `themes.dark`); переключатель — `ThemeToggle`, выбор хранится в браузере. Тест `themes.test.ts` проверяет контраст текста (WCAG AA, 4.5:1) в обеих темах.
- Ошибки API показываются через `ErrorNotice`: пользователь видит код, модуль и ID запроса и может скопировать их одной кнопкой.

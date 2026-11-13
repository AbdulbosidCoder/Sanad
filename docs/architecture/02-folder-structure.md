# 2. Структура проекта

```text
sanad/
├── backend/
│   ├── app/
│   │   ├── main.py                  # создание FastAPI-приложения, подключение роутеров
│   │   ├── core/                    # общее ядро, без бизнес-логики
│   │   │   ├── config.py            # настройки (pydantic-settings), dev/prod
│   │   │   ├── db.py                # engine, session, Unit of Work
│   │   │   ├── security.py          # хэширование, JWT, CSRF
│   │   │   ├── permissions.py       # RBAC: require_permission(), object-level проверки
│   │   │   ├── events.py            # шина событий + outbox
│   │   │   ├── idempotency.py       # Idempotency-Key middleware
│   │   │   ├── rate_limit.py
│   │   │   ├── i18n.py              # определение языка запроса, fallback
│   │   │   ├── errors.py            # единый формат ошибок (RFC 9457)
│   │   │   └── pagination.py
│   │   ├── modules/
│   │   │   ├── identity/
│   │   │   │   ├── api/             # routers.py, schemas.py
│   │   │   │   ├── service.py
│   │   │   │   ├── repository.py
│   │   │   │   ├── models.py
│   │   │   │   ├── events.py
│   │   │   │   ├── tasks.py
│   │   │   │   └── tests/
│   │   │   ├── stores/  catalog/  i18n/  inventory/  search/
│   │   │   ├── cart/  orders/  payments/  reviews/  engagement/
│   │   │   ├── recommendations/  analytics/  support/
│   │   │   └── notifications/  media/  audit/  platform/
│   │   │       # payments/providers/: base.py (PaymentProvider), fake.py,
│   │   │       #   позже uzcard.py, humo.py, visa.py
│   │   │       # i18n/translators/: base.py (Translator), llm.py, noop.py
│   │   └── workers/
│   │       ├── celery_app.py
│   │       └── beat_schedule.py
│   ├── migrations/                  # Alembic
│   ├── tests/                       # интеграционные и e2e API-тесты
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── apps/
│   │   ├── web/                     # покупатель
│   │   ├── seller/                  # продавец
│   │   └── admin/                   # админ, поддержка, финансы, tech ops
│   ├── packages/
│   │   ├── ui/                      # дизайн-система: tokens.ts, компоненты
│   │   ├── api-client/              # сгенерирован из OpenAPI
│   │   ├── i18n/                    # uz.json, ru.json, en.json
│   │   └── config/                  # eslint, tsconfig, tailwind preset
│   ├── package.json  pnpm-workspace.yaml  turbo.json
│   └── Dockerfile
├── infra/
│   ├── docker/                      # nginx.conf, postgres init, minio init
│   ├── compose/
│   │   ├── docker-compose.yml       # базовый
│   │   ├── docker-compose.dev.yml   # dev-переопределения (hot reload, mailpit)
│   │   └── docker-compose.prod.yml
│   ├── monitoring/                  # prometheus, grafana дашборды
│   └── scripts/                     # backup.sh, restore.sh, seed.py
├── docs/
│   ├── architecture/                # этот пакет
│   └── adr/                         # записи архитектурных решений
├── .github/workflows/               # CI: lint, typecheck, tests, build
├── .env.example
├── Makefile                         # make up, make test, make migrate…
└── README.md
```

## Правила

- Один файл — одна ответственность. Ориентир: файл длиннее ~400 строк дробим.
- `core/` не импортирует `modules/`. Модули импортируют `core/` и **только** `service`-слой других модулей.
- Тесты модуля лежат рядом с модулем; сквозные сценарии (checkout целиком) — в `backend/tests/`.
- Тексты интерфейса только в `packages/i18n`, нигде не захардкожены (проверяется ESLint-правилом).

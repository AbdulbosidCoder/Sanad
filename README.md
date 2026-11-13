# Sanad

Мультивендорный маркетплейс (uz / ru / en): покупатели, продавцы, администрирование и поддержка.

## Быстрый старт

```bash
make up        # создаёт .env из .env.example, собирает и запускает все сервисы
make ps        # статус и health каждого контейнера
make test      # тесты бэкенда
make help      # все команды
```

- Сайт покупателя: http://localhost
- Панель продавца: http://localhost/seller
- Админка и карта системы: http://localhost/admin
- API и документация: http://localhost/api/v1/docs
- Состояние БД и Redis: http://localhost/health/ready
- Карта модулей бэкенда (dev): http://localhost:8000/api/v1/system/modules
- Письма в dev (mailpit): http://localhost:8025

## Документация

- [Как устроена система и где искать баг](docs/architecture/11-how-it-works.md) — начните отсюда.
- [Архитектурный пакет](docs/architecture/README.md) и [решения (ADR)](docs/adr/README.md).
- [Бэкенд](backend/README.md) и [фронтенд](frontend/README.md).

## Структура

| Папка | Что внутри |
|---|---|
| `backend/` | API на Python + FastAPI (модульный монолит) |
| `frontend/` | Next.js + TypeScript: сайт покупателя, панель продавца, админка, общая дизайн-система |
| `infra/` | Docker Compose, nginx, скрипты |
| `docs/` | Архитектура и ADR |

## CI

GitHub Actions (`.github/workflows/ci.yml`) запускается на каждый PR и push в `main`:

- **Docs** — синтаксис Mermaid-диаграмм и относительные ссылки в Markdown.
- **Secret scan** — gitleaks по всей истории.
- **Backend** — ruff, mypy, границы модулей, миграции на чистой PostgreSQL, pytest, pip-audit.
- **Frontend** — ESLint, TypeScript, тесты (Vitest), сборка всех трёх приложений.
- **Docker Compose** — проверка dev и prod конфигураций.

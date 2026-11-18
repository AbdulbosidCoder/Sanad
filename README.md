# Sanad

Мультивендорный маркетплейс (uz / ru / en): покупатели, продавцы, администрирование и поддержка.

## Быстрый старт

```bash
make up        # создаёт .env из .env.example, собирает и запускает все сервисы
make ps        # статус и health каждого контейнера
make seed      # демо-данные (в dev грузятся и сами при `make up`)
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

## Демо-данные

В dev после миграций автоматически загружаются тестовые данные (повторный запуск ничего не дублирует): 10 пользователей, 5 заявок продавцов, 3 магазина, 10 категорий, 10 брендов, 10 товаров с размерами, фото с 7 сторон, фото покупателей и остатками (есть «мало на складе» и «нет в наличии»), 7 заказов во всех состояниях (оплачен, отправлен, доставлен, не оплачен, оплата не прошла, отменён с возвратом денег, запрос возврата).

Как купить на тестовых платежах: корзина → `POST /api/v1/checkout` (заголовок `Idempotency-Key`) → `POST /api/v1/payments/{id}/confirm` с `{"outcome": "succeeded"}` или `"failed"`.

Пароль у всех: `Demo12345!`

| Вход | Роль |
|---|---|
| `admin@example.com` | super_admin |
| `moderator@example.com` | admin |
| `support@example.com` | support_lead |
| `seller1@example.com`, `seller2@…`, `seller3@…` | владельцы магазинов Sneaker Lab, Urban Step, Outdoor Uz |
| `buyer1@example.com` … `buyer4@example.com` | покупатели |

Без Docker: укажите `DATABASE_URL` в `.env` в корне репозитория, затем `cd backend && alembic upgrade head && python -m app.seed`. В `staging`/`prod` команда отказывается работать.

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

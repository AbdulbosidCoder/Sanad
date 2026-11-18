# Модуль `platform`

Панель эксплуатации для роли `developer` (и админов): состояние фоновых очередей без личных данных.
Позже здесь будут настройки платформы и feature flags.

## Связи

**Зависит от:** `i18n` (очередь переводов), `notifications` (очередь писем), `audit` (перезапуск)

## API

| Метод | Путь | Право | Что |
|---|---|---|---|
| GET | `/admin/ops` | `ops.read` | Очереди `translations` и `emails` по статусам, доступность БД и Redis |
| POST | `/admin/ops/queues/{translations\|emails}/retry` | `ops.jobs_retry` | `failed` → снова `pending` (в аудит) |

## Фоновые задачи (Celery beat)

| Задача | Как часто | Что делает |
|---|---|---|
| `orders.expire_unpaid` | 5 мин | Отменяет неоплаченные заказы и освобождает резерв |
| `i18n.translate_pending` | 1 мин | Переводит товары |
| `notifications.send_emails` | 1 мин | Отправляет письма |

Если `failed` растёт — смотрите `last_error` в таблице очереди (README модулей `i18n`, `notifications`).

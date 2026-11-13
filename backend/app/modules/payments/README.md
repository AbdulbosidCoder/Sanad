# Модуль `payments`

Платежи через PaymentProvider (V1: FakeProvider), вебхуки, возвраты денег, ledger.

## Связи

**Зависит от (вызывает их `service.py`):**
- `audit`

**Используется модулями:**
- `orders`

**Публикует события:**
- `PaymentSucceeded`
- `PaymentFailed`
- `RefundCompleted`

**Слушает события:**
- —

**Таблицы:** `payments`, `payment_attempts`, `refunds`, `webhook_events`, `ledger_entries`

## Файлы

| Файл | Что внутри |
|---|---|
| `module.py` | Описание модуля и его связей (видно в `GET /api/v1/system/modules`) |
| `api.py` | HTTP-эндпоинты: принимают запрос, проверяют права, вызывают `service.py` |
| `service.py` | Бизнес-логика. Единственная точка входа для других модулей |
| `events.py` | События, которые модуль публикует и на которые подписан |
| `models.py`, `repository.py`, `schemas.py` | Появятся вместе с функциональностью |

## Где искать баг

Симптомы, которые обычно ведут сюда: оплата зависла в pending, двойное списание, возврат денег не прошёл.

В ошибке API и в логах ищите `"module": "payments"` и `request_id`.

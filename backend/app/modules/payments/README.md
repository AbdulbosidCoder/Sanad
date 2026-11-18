# Модуль `payments`

Платежи через `PaymentProvider` (V1: `FakeProvider`), вебхуки, возвраты денег с разделением обязанностей, ledger.

## Связи

**Зависит от:** `audit` (позже)
**Используется модулями:** `orders`
**Публикует события:** `PaymentSucceeded`, `PaymentFailed`, `RefundCompleted` (их слушает `orders`)
**Таблицы:** `payments`, `payment_attempts`, `refunds`, `webhook_events`, `ledger_entries`

## Эндпоинты

| Метод | Путь | Кто | Что делает |
|---|---|---|---|
| GET | `/payments/methods` | все | Включённые способы оплаты (V1: `["fake"]`) |
| GET | `/payments/{id}` | владелец | Статус платежа |
| POST | `/payments/{id}/confirm` | владелец | Только тестовый платёж: `{"outcome": "succeeded" \| "failed"}` |
| POST | `/webhooks/payments/{provider}` | провайдер | Подписанный вебхук; повтор того же `event_id` игнорируется |
| GET | `/admin/payments`, `/admin/refunds`, `/admin/ledger` | `payments.read` | Транзакции, возвраты, проводки |
| POST | `/admin/refunds/{id}/approve` \| `/reject` | 🔒 `refunds.approve` | Тот, кто запросил возврат, одобрить его не может |

## Как подключить Uzcard / Humo / Visa

1. Класс в `providers.py` с методами `create_payment`, `refund`, `verify_webhook` (см. `PaymentProvider`).
2. Строка в `registry()` и его ключи в настройках.
3. Всё. `orders` и checkout не меняются: они знают только `payments.service`.

`FakeProvider` выключен в production (`FAKE_PAYMENTS_ENABLED=false`; запуск с `true` в prod падает). Все его платежи `is_test = true`. Вебхук подписывается HMAC-SHA256 ключом `FAKE_PAYMENTS_WEBHOOK_SECRET` в заголовке `X-Fake-Signature`.

## Ledger

Только вставка, суммы со стороны магазина: `sale` +, `commission` −, `refund` −, `commission_refund` +. Баланс магазина: `service.store_balance`.

## Где искать баг

Оплата зависла в `pending` — пришёл ли вебхук (`webhook_events`), есть ли попытки (`payment_attempts`). Ищите `"module": "payments"`.

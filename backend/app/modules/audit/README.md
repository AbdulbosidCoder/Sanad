# Модуль `audit`

Неизменяемый журнал чувствительных действий: кто, что, над чем и когда.

## Связи

Ни от кого не зависит. Его `service.record(...)` вызывают другие модули **в своей транзакции**:
действие и запись журнала сохраняются вместе или вместе откатываются.

**Таблица:** `audit_logs`

## Что записывается

| action | Где |
|---|---|
| `users.block`, `users.unblock`, `rbac.grant`, `rbac.revoke` | identity (админка пользователей) |
| `stores.approve`, `stores.reject`, `stores.suspend`, `stores.reactivate` | stores |
| `orders.status_override`, `returns.decide` | orders |
| `refunds.approve`, `refunds.reject` | payments |
| `reviews.hide`, `reviews.unhide` | reviews |
| `support.assign` | support |

## Защита от подделки

- Триггер в БД запрещает `UPDATE` и `DELETE` (ошибка `audit_logs is append-only`).
- Каждая запись хранит хеш предыдущей (`prev_hash`) и свой (`hash` = SHA-256 от prev + содержимого).
  Запись пишется под `pg_advisory_xact_lock`, поэтому цепочка всегда одна.
- `GET /admin/audit/verify` пересчитывает цепочку и называет `seq`, где она порвалась.

## API

| Метод | Путь | Кто | Что |
|---|---|---|---|
| GET | `/admin/audit?actor_id=&action=&target_type=&target_id=&since=` | `audit.read` — всё; `audit.read_finance` — только payments/refunds/returns/orders | Журнал, новые сверху |
| GET | `/admin/audit/verify` | `audit.read` | Проверка цепочки |

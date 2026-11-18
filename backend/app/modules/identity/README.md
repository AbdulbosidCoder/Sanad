# Модуль `identity`

Регистрация, вход, токены и сессии, роли и права (RBAC).

## Связи

**Зависит от (вызывает их `service.py`):**
- —

**Используется модулями:**
- `stores`
- `support`
- `notifications`

**Публикует события:**
- `UserRegistered`
- `LoginSucceeded`
- `LoginFailed`

**Слушает события:**
- —

**Таблицы:** `users`, `roles`, `permissions`, `role_permissions`, `user_roles`, `sessions`, `refresh_tokens`, `user_credentials`, `addresses`

## Эндпоинты

| Метод | Путь | Что делает |
|---|---|---|
| POST | `/auth/register` | Регистрация (email и/или телефон `+998…`), сразу выполняет вход, роль `customer` |
| POST | `/auth/login` | Вход по email или телефону. 5 неудач подряд → блокировка на 15 минут (429) |
| POST | `/auth/refresh` | Новый access + ротация refresh-cookie. Нужен заголовок `X-CSRF-Token` |
| POST | `/auth/logout` | Отзывает сессию; access-токен перестаёт работать сразу |
| GET/PATCH | `/me` | Профиль, роли и права; менять можно только `full_name` и `locale` |
| POST | `/me/password` | Смена пароля, выход на всех других устройствах |
| GET/DELETE | `/me/sessions[/{id}]` | Активные устройства, выход на одном из них |
| GET/POST/PATCH/DELETE | `/me/addresses[/{id}]` | Адреса (до 20); первый становится основным |

Как это устроено: access JWT (EdDSA, 15 мин) в теле ответа → клиент держит его в памяти и шлёт `Authorization: Bearer`. Refresh — только в HttpOnly-cookie `sanad_refresh` (путь `/api/v1/auth`). Повтор уже использованного refresh-токена = кража → вся сессия отзывается, поэтому фронтенд должен вызывать `/auth/refresh` **по одному запросу за раз**. На каждом запросе сессия и права читаются из БД, так что выход, блокировка и смена ролей действуют мгновенно.

Для других модулей: `Depends(get_principal)` и `Depends(require_permission("..."))` из `app/core/auth.py` (не из этого модуля).

## Роли и первый админ

Каталог ролей и прав — `rbac.py` (код-версия [матрицы RBAC](../../../../docs/architecture/04-rbac-matrix.md)). API записывает его в БД при каждом старте. Первый админ: зарегистрироваться через API, затем

```bash
python -m app.modules.identity.cli grant-role you@example.com super_admin
```

## Файлы

| Файл | Что внутри |
|---|---|
| `module.py` | Описание модуля и его связей (видно в `GET /api/v1/system/modules`) |
| `api.py` | HTTP-эндпоинты, cookie и CSRF; вызывают `service.py` |
| `service.py` | Бизнес-логика. Единственная точка входа для других модулей |
| `repository.py` | Запросы к БД |
| `models.py` | Таблицы (пароль — в `user_credentials`, не в `users`, ради 2FA/passkeys в V3) |
| `schemas.py` | Тела запросов/ответов; входные схемы запрещают лишние поля |
| `rbac.py` | Встроенные роли и права |
| `cli.py` | `sync-rbac`, `grant-role` |
| `events.py` | События, которые модуль публикует и на которые подписан |

## Ещё не сделано (этап 1)

- Подтверждение email/телефона и восстановление пароля — нужен модуль `notifications` (отправка писем/SMS).
- Rate limit по IP на `/auth/*` — нужен Redis; блокировка по аккаунту уже работает.
- Журнал аудита входов сотрудников — модуль `audit`.
- События `UserRegistered`, `LoginSucceeded`, `LoginFailed` пока только пишутся в лог — шины событий (outbox) ещё нет.
- Админские эндпоинты (блокировка пользователей, выдача ролей) — этап 8.

## Где искать баг

Симптомы, которые обычно ведут сюда: не получается войти, «нет доступа» (403), разлогинивает, не сохраняется язык или адрес.

В ошибке API и в логах ищите `"module": "identity"` и `request_id`.

## Админка пользователей

| Метод | Путь | Право | Что |
|---|---|---|---|
| GET | `/admin/users?q=&status=&role=` | `users.read` | Поиск по email, телефону, имени |
| GET | `/admin/users/{id}` | `users.read` | Пользователь и его роли |
| POST | `/admin/users/{id}/block` / `unblock` | `users.block` 🔒 | Блокировка сразу завершает все сессии; себя нельзя, super admin — только super admin |
| GET | `/admin/roles` | `users.read` | Роли и их права |
| PUT / DELETE | `/admin/users/{id}/roles/{code}` | `rbac.manage` 🔒 | Выдать / забрать роль платформы; последнего super admin и роль customer забрать нельзя |

Всё это пишется в журнал аудита.

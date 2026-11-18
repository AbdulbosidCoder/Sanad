# Модуль `stores`

Магазины, заявки продавцов, сотрудники магазина и проверка «к какому магазину у вас есть доступ».

## Связи

**Зависит от (вызывает их `service.py`):**
- `identity` — права store-ролей, поиск пользователя по email/телефону
- `audit` — запись чувствительных действий (появится вместе с модулем `audit`)

**Используется модулями:**
- `catalog`, `inventory` — `store_access(...)` для всех `/seller/...` эндпоинтов, `active_store_ids()` для витрины
- `orders` (этап 5)

**Публикует события:** `SellerApplicationSubmitted`, `StoreApproved`, `StoreSuspended` (пока только в лог)

**Таблицы:** `stores`, `store_memberships`, `seller_applications`

## Эндпоинты

| Метод | Путь | Кто | Что делает |
|---|---|---|---|
| GET | `/stores/{slug}` | все | Шапка страницы магазина (только активные) |
| POST/GET | `/seller/applications` | любой вошедший | Подать заявку / мои заявки. Одна заявка на рассмотрении за раз |
| GET | `/seller/stores` | сотрудник | Мои магазины, роль и права в каждом |
| GET/PATCH | `/seller/store` | сотрудник / `store.settings_manage` | Настройки магазина |
| GET/POST | `/seller/staff` | владелец | Сотрудники; добавить по email/телефону с ролью `seller_manager` или `seller_staff` |
| DELETE | `/seller/staff/{user_id}` | владелец | Убрать сотрудника (владельца убрать нельзя) |
| GET | `/admin/seller-applications?status=` | `seller_applications.review` | Очередь заявок |
| POST | `/admin/seller-applications/{id}/approve` \| `/reject` | 🔒 то же | Одобрение создаёт магазин и делает заявителя владельцем |
| GET | `/admin/stores?status=` | `stores.suspend` | Все магазины |
| POST | `/admin/stores/{id}/suspend` \| `/reactivate` | 🔒 `stores.suspend` | Приостановка: товары скрыты от покупателей, изменения в магазине запрещены |

## Как работает доступ продавца

1. Фронтенд берёт список магазинов из `GET /seller/stores` и шлёт выбранный в заголовке `X-Store-Id`. Если магазин у пользователя один, заголовок можно не слать.
2. `store_access("products.write")` проверяет: пользователь — сотрудник этого магазина, его store-роль даёт право, магазин активен.
3. Чужой магазин отвечает **404**, а не 403, чтобы нельзя было узнать, что он существует.

Store-роли и их права — в `identity/rbac.py` (`seller_owner`, `seller_manager`, `seller_staff`).

## Файлы

| Файл | Что внутри |
|---|---|
| `module.py` | Описание модуля и его связей (видно в `GET /api/v1/system/modules`) |
| `api.py` | HTTP-эндпоинты |
| `service.py` | Бизнес-логика и `store_access` для других модулей |
| `repository.py` | Запросы к БД |
| `models.py` | Таблицы |
| `schemas.py` | Тела запросов/ответов; входные схемы запрещают лишние поля |

## Ещё не сделано

- Запись одобрений, приостановок и смены сотрудников в журнал аудита — модуль `audit` (этап 8).
- Загрузка документов к заявке файлами — модуль `media`; сейчас `documents` — свободный JSON.
- Изменение комиссии магазина админом.

## Где искать баг

Симптомы: продавец не видит свой магазин или получает 404/403 в панели, заявка не одобряется, товары магазина пропали с витрины (магазин приостановлен?).

В ошибке API и в логах ищите `"module": "stores"` и `request_id`. Коды: `STORES.STORE_REQUIRED` (не передан `X-Store-Id`), `STORES.STORE_NOT_FOUND`, `STORES.FORBIDDEN`, `STORES.STORE_SUSPENDED`.

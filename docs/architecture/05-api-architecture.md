# 5. Архитектура API

## 5.1 Общие правила

- **REST, JSON, версия в пути:** `/api/v1/...`. Ломающие изменения — только в `/api/v2/`; в рамках v1 разрешено лишь добавлять поля и эндпоинты.
- **OpenAPI** генерируется FastAPI автоматически; из него генерируется TypeScript-клиент (`packages/api-client`). CI падает, если схема изменилась ломающим образом (`oasdiff`).
- **Разделение по аудиториям** (префиксы), чтобы права и rate limit настраивались отдельно:
  - `/api/v1/...` — публичное и покупательское API;
  - `/api/v1/seller/...` — панель продавца, магазин определяется заголовком `X-Store-Id` + проверкой членства;
  - `/api/v1/admin/...` — админка, поддержка, финансы, тех. операции;
  - `/api/v1/webhooks/...` — входящие вебхуки провайдеров.
- **Язык:** `Accept-Language: uz|ru|en` (или `?lang=`). Ответ содержит перевод на этом языке с fallback на оригинал.
- **Ошибки** в формате RFC 9457 (`application/problem+json`): `type`, `title`, `status`, `detail`, `code`, `errors[]`. `title` и `detail` локализуются.
- **Пагинация:** курсорная для лент и каталога (`?cursor=&limit=`), offset — только в админских таблицах.
- **Идемпотентность:** `Idempotency-Key` обязателен для `POST /checkout`, платежей и возвратов. Ключ и ответ хранятся в Redis 24 ч.
- **Деньги** передаются строкой (`"125000.00"`) + `currency`, чтобы не терять точность в JS.
- **Request ID** (`X-Request-Id`) на каждом ответе; он же в логах и в аудите.

## 5.2 Аутентификация (готова к V2/V3)

- Веб: **access token** (JWT, 15 мин) в памяти + **refresh token** в `HttpOnly; Secure; SameSite=Lax` cookie, с **ротацией** и обнаружением повторного использования (повтор старого refresh → отзыв всей сессии).
- Мобильные/десктоп (V2): тот же поток, refresh хранится в Keychain/Keystore и передаётся в теле запроса.
- Сессия — отдельная сущность (`Session`) с устройством и IP, поэтому V3 (управление устройствами, 2FA, passkeys) добавляется как новые шаги входа, без изменения остальных модулей. Поток входа сразу спроектирован как многошаговый: `POST /auth/login` может вернуть `{"next_step": "otp"}` вместо токенов.

## 5.3 Основные группы эндпоинтов

### Auth и профиль
| Метод | Путь | Описание |
|---|---|---|
| POST | `/auth/register` | Регистрация (email/телефон, пароль, язык) |
| POST | `/auth/login` | Вход, может вернуть следующий шаг (V3) |
| POST | `/auth/refresh` | Ротация токенов |
| POST | `/auth/logout` | Отзыв текущей сессии |
| POST | `/auth/password/forgot`, `/auth/password/reset` | Восстановление |
| POST | `/auth/verify-email` | Подтверждение email |
| GET/PATCH | `/me` | Профиль, язык |
| GET/DELETE | `/me/sessions[/{id}]` | Активные сессии |
| CRUD | `/me/addresses` | Адреса |
| GET/PATCH | `/me/notifications`, `/me/notification-settings` | Уведомления |

### Каталог и поиск
| Метод | Путь | Описание |
|---|---|---|
| GET | `/products` | Поиск и фильтры: `q, category, brand, store, price_min, price_max, in_stock, rating_min, sort=price_asc|price_desc|popular|newest` |
| GET | `/products/suggest?q=` | Автодополнение (из Redis-кэша) |
| GET | `/products/{slug}` | Карточка товара |
| GET | `/products/{id}/reviews` | Отзывы |
| GET | `/categories`, `/brands`, `/stores/{slug}` | Справочники и витрина магазина |
| GET | `/home` | Главная: блоки «Рекомендуем», «Тренды», «Хиты недели» (одним запросом) |
| POST | `/events/view` | Трекинг просмотра (батч) |

### Покупатель
| Метод | Путь | Описание |
|---|---|---|
| GET/POST/PATCH/DELETE | `/cart`, `/cart/items/{id}` | Корзина (работает и для гостя через `guest_token`, объединяется при входе) |
| POST | `/checkout/preview` | Расчёт: разбиение по магазинам, налоги, итог |
| POST | `/checkout` | Создание заказа + резерв остатков + создание платежа. **Idempotency-Key** |
| POST | `/payments/{id}/confirm` | Подтверждение (для Fake — выбор исхода) |
| GET | `/orders`, `/orders/{id}` | История и трекинг |
| POST | `/orders/{id}/cancel` | Отмена до отправки |
| POST | `/orders/{id}/items/{item_id}/return` | Запрос возврата |
| CRUD | `/favorites` | Избранное |
| POST | `/products/{id}/reviews` | Отзыв (только по купленному товару) |
| CRUD | `/support/tickets`, `/support/tickets/{id}/messages` | Обращения |

### Продавец (`/seller`)
| Метод | Путь | Описание |
|---|---|---|
| POST | `/seller/applications` | Заявка на открытие магазина |
| GET/PATCH | `/seller/store` | Настройки магазина |
| CRUD | `/seller/products`, `/seller/products/{id}/variants`, `/images` | Товары (загрузка изображений через presigned URL) |
| PATCH | `/seller/products/{id}/translations/{locale}` | Ручная правка перевода |
| GET/PATCH | `/seller/inventory` | Остатки, пороги low-stock |
| GET | `/seller/orders`, PATCH `/seller/orders/{id}/status` | Заказы и статусы |
| GET/PATCH | `/seller/returns` | Возвраты |
| GET | `/seller/analytics/summary?period=day|week|month` | Продажи, выручка, заказы |
| GET | `/seller/analytics/products` | Бестселлеры, просмотры, показы, конверсия, «много просмотров — мало продаж» |
| GET | `/seller/analytics/low-stock` | Товары с низким остатком |
| CRUD | `/seller/staff` | Сотрудники магазина (только owner) |

### Админка (`/admin`)
| Группа | Пути |
|---|---|
| Пользователи | `/admin/users`, `/admin/users/{id}/block`, `/admin/users/{id}/roles` |
| Магазины | `/admin/stores`, `/admin/seller-applications/{id}/approve|reject`, `/admin/stores/{id}/suspend` |
| Каталог | `/admin/categories`, `/admin/brands`, `/admin/products/{id}/moderate` |
| Поддержка | `/admin/support/tickets`, `/assign`, `/messages` |
| Финансы | `/admin/payments`, `/admin/refunds`, `/admin/refunds/{id}/approve`, `/admin/ledger` |
| Тех. операции | `/admin/ops/health`, `/admin/ops/jobs`, `/admin/ops/jobs/{id}/retry`, `/admin/ops/integrations` |
| Аудит | `/admin/audit-logs` |
| Настройки | `/admin/settings`, `/admin/roles`, `/admin/permissions` |

### Служебные
`GET /health/live`, `GET /health/ready` (БД, Redis, хранилище), `GET /metrics` (только из внутренней сети), `POST /webhooks/payments/{provider}`.

## 5.4 Абстракция платежей

```python
class PaymentProvider(Protocol):
    code: str                      # "fake", "uzcard", "humo", "visa"
    is_test: bool

    async def create_payment(self, payment: PaymentRequest) -> ProviderPayment: ...
    async def get_status(self, provider_payment_id: str) -> PaymentStatus: ...
    async def refund(self, refund: RefundRequest) -> ProviderRefund: ...
    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> WebhookEvent: ...
```

- Модуль `orders` знает только `PaymentService`, а не провайдеров. Новый провайдер — новый класс + запись в реестре + настройки; заказы и checkout не меняются.
- **FakeProvider** имитирует `succeeded`, `failed`, `pending` (с вебхуком через N секунд) и возвраты. Все его платежи помечены `is_test = true`, в интерфейсе — бейдж «Тестовый платёж», в production он отключён флагом конфигурации.
- Вебхуки: проверка HMAC-подписи и времени, дедупликация по `event_id` (`WebhookEvent`), обработка в воркере.
- Данные карты не проходят через наш бэкенд: в будущем — страница/токенизация провайдера (redirect или hosted fields). Храним только токен и маску `**** 1234`.

## 5.5 Абстракция перевода

```python
class Translator(Protocol):
    async def translate(self, text: str, source: Locale, target: Locale, *, kind: str) -> str: ...
```

Продавец создаёт товар на одном языке → событие `ProductCreated` → задача переводит на два других языка → `ProductTranslation.origin = "machine"`. Если продавец правит перевод вручную, `origin = "manual"` и автоперевод его больше не перезаписывает. При изменении оригинала машинные переводы пересоздаются, ручные помечаются как «требует проверки» (через `source_hash`).

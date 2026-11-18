# Модуль `reviews`

Отзывы и рейтинг товара. Писать может только тот, кому товар **доставили** — это защита от
накруток. Фото к отзыву — это фото покупателя в каталоге (`POST /products/{slug}/buyer-photos`).

## Связи

**Зависит от:** `orders` (`purchased_item` — доказательство покупки), `catalog` (магазин товара,
запись `rating_avg`/`rating_count`), `identity` (имя автора), `stores` (доступ продавца)

**Публикует:** `ReviewPublished` · **Таблицы:** `reviews`

## Правила

- Один отзыв на покупателя и товар (уникальный индекс), автор может изменить или удалить его.
- `fit`: `small` / `true` / `large` — как сидит размер; на странице товара видна сводка.
- Магазин отвечает на отзыв (`products.write`), ответ можно поправить.
- Сотрудник с `reviews.hide` скрывает отзыв с причиной; скрытые не влияют на рейтинг.
- После каждого изменения рейтинг товара пересчитывается в той же транзакции.

## API

| Метод | Путь | Кто | Что |
|---|---|---|---|
| GET | `/products/{id}/reviews?rating=&sort=` | все | Опубликованные отзывы |
| GET | `/products/{id}/reviews/summary` | все | Средний, распределение по звёздам, посадка |
| GET | `/products/{id}/reviews/can-review` | все | Показывать ли кнопку «Оставить отзыв» |
| POST | `/products/{id}/reviews` | покупатель | Новый отзыв (403 `REVIEWS.NOT_PURCHASED`, 409 `ALREADY_REVIEWED`) |
| GET / PATCH / DELETE | `/me/reviews`, `/me/reviews/{id}` | автор | Свои отзывы |
| GET | `/seller/reviews?unanswered=` | магазин | Отзывы о товарах магазина |
| PUT | `/seller/reviews/{id}/reply` | `products.write` | Ответ магазина |
| GET | `/admin/reviews?status=&max_rating=` | `reviews.hide` | Модерация |
| POST | `/admin/reviews/{id}/hide`, `/unhide` | `reviews.hide` | Скрыть / вернуть |

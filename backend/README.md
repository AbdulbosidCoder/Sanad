# Backend (FastAPI)

Модульный монолит: один сервис, 18 модулей в `app/modules/`. Как всё связано и как искать баги — [docs/architecture/11-how-it-works.md](../docs/architecture/11-how-it-works.md).

## Запуск без Docker

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
export DATABASE_URL=postgresql+asyncpg://sanad:sanad@localhost:5432/sanad REDIS_URL=redis://localhost:6379/0
alembic upgrade head
uvicorn app.main:app --reload
```

## Проверки (то же, что в CI)

```bash
ruff check . && ruff format --check .   # стиль и типичные ошибки
mypy app                                # типы
lint-imports                            # core не зависит от модулей
pytest                                  # тесты (нужны PostgreSQL и Redis)
pip-audit --skip-editable               # уязвимости в зависимостях
```

## Как добавить функциональность в модуль

1. Таблицы — `app/modules/<модуль>/models.py`, затем `alembic revision --autogenerate -m "..."`.
2. Запросы в БД — `repository.py`.
3. Бизнес-правила — `service.py`. Ожидаемые ошибки: `raise AppError("<модуль>", "CODE", "текст", status=...)`.
4. HTTP — `api.py`, только вызовы `service.py`.
5. Нужен другой модуль — импортируйте его `service.py` и добавьте его в `depends_on` в `module.py`.
6. Обновите `README.md` модуля, если поменялись связи.

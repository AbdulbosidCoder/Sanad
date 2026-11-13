# Sanad

Мультивендорный маркетплейс (uz / ru / en): покупатели, продавцы, администрирование и поддержка.

Сейчас проект на этапе проектирования. Архитектурный пакет: [docs/architecture](docs/architecture/README.md).

## CI

GitHub Actions (`.github/workflows/ci.yml`) запускается на каждый PR и push в `main`:

- **Docs** — проверка синтаксиса всех Mermaid-диаграмм и относительных ссылок в Markdown.
- **Secret scan** — gitleaks по всей истории.
- **Backend** — включается сам, когда появится `backend/pyproject.toml`: ruff, mypy, границы модулей, миграции Alembic на чистой PostgreSQL, pytest с покрытием, pip-audit.
- **Frontend** — включается сам, когда появится `frontend/package.json`: lint, typecheck, тесты, сборка.
- **Docker Compose** — проверка dev и prod конфигураций, когда появится `infra/compose/`.

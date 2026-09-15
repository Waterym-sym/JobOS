# Database migrations

Alembic is the only executable database migration entry point. The SQL file in
`contracts/db` remains a comparison contract and must never be executed.

Review before running, then apply explicitly:

```powershell
python -m alembic upgrade head
```

Production sequencing remains backup → migration check → infrastructure →
Alembic migration → service upgrade. API startup never applies migrations.

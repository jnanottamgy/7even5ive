# PortMax

One college portal in, five read-only tools out, the same shape for every college:
`get_attendance`, `get_timetable`, `get_marks`, `get_results`, `get_profile`.

The plan, and why each piece is the way it is, lives in [`../docs/portmax.md`](../docs/portmax.md).

## Develop

```bash
uv sync
uv run pytest
uv run ruff check .
uv run mypy
```

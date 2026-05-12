"""Запускает daily_flow в режиме `Flow.serve()` внутри Prefect-worker контейнера.

Prefect 3.x требует image/remote storage для `.deploy()` с process work pool;
для нашего сценария (всё в docker-compose, код через bind-mount) проще
использовать `.serve()` — он:
  - регистрирует deployment в Prefect server (виден в UI),
  - запускает встроенный scheduler по cron'у в этом же процессе,
  - не требует отдельного work pool / worker.

Cron и TZ читаются из env (FRAUD_CRON, FRAUD_CRON_TZ), как и в оригинальном
`orchestration/deployment.py`. Имя deployment'а — `FRAUD_DEPLOYMENT_NAME`.

Подразумевается работа из `/repo` (см. `docker-compose.yml` working_dir).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.environ.get("REPO_DIR", "/repo"))

from orchestration.daily_flow import daily_flow


def main() -> None:
    name = os.environ.get("FRAUD_DEPLOYMENT_NAME", "nightly-retrain")
    cron = os.environ.get("FRAUD_CRON", "0 4 * * *")
    tz = os.environ.get("FRAUD_CRON_TZ", "Europe/Moscow")
    tags = os.environ.get("FRAUD_DEPLOYMENT_TAGS", "fraud,daily").split(",")

    try:
        from prefect.client.schemas.schedules import CronSchedule
    except ImportError:
        from prefect.server.schemas.schedules import CronSchedule  # type: ignore

    print(f"serving deployment={name!r} cron={cron!r} tz={tz!r} tags={tags}", flush=True)
    daily_flow.serve(
        name=name,
        schedules=[CronSchedule(cron=cron, timezone=tz)],
        tags=tags,
    )


if __name__ == "__main__":
    sys.exit(main() or 0)

# CLAUDE.md — гайд для будущих сессий

Антифрод-backend на FastAPI с тремя независимыми скоринг-pipeline'ами + интеграцией с daily-retrain pipeline. Документ описывает то, что **невозможно прочитать из кода**: архитектурные решения, гочи и конвенции.

## Что это

Backend получает события и возвращает банку **скор фрода 0..10** + рекомендуемый `decision` (`safe`/`review`/`sms`/`biometry`).

| Endpoint | Pipeline |
|---|---|
| `POST /score/behavior` | 7 правил → fail-fast → PyTorch FraudMLP |
| `POST /score/chat`     | regex + meta-сигналы → если триггер → LLM (Ollama) |
| `POST /score/merchant` | GET к merchant_mock → правила → LLM по карточке + отзывам |
| `POST /admin/reload-model` | Bearer-auth swap модели + customer_features (для daily_flow) |
| `POST /admin/labels-batch` | Bearer-auth ручная разметка → `~/fraud/labels{,_mobile}/` |

ML-модели **не обучаются здесь** — только инференс. Обучение в соседних проектах `../AntiFraudMLMobile/` и `../AntiFraudMLWeb/`.

## Архитектурные решения (НЕ менять без обсуждения)

### 1. Fail-fast: rules → ML только для чистых

Если `apply_rules(event)` дал суммарный вес `≥ RULE_THRESHOLD_BEHAVIOR` → возвращаем чисто rule-скор без вызова нейронки. Логика: критичные сигналы (VPN+гео-телепорт+root) уже сами по себе доказательны, нейронка только удлинит latency. Нейронка ловит **тонкие** аномалии, когда правила чисты.

То же для chat (rules-сумма ≥ threshold → зовём LLM, иначе только rules) и merchant (правила сработали ИЛИ домен молодой → LLM).

### 2. Загрузка моделей при старте, singleton в `app.state`

`create_app(load_models=True)` грузит `mobile_best.pt` и `web_best.pt` в lifespan — один раз, держим в памяти. **Никогда** не грузить модель в хендлере. Для тестов без моделей: `create_app(load_models=False)`.

### 3. `ModelLoader` — Protocol, два класса

`LocalFileLoader` (default, файлы из `./models/*.pt`) и `MlflowLoader` (`FRAUD_MODEL_BACKEND=mlflow` → `models:/fraud_mlp_{web,mobile}/Production`) реализуют один Protocol. Switcher в `app.deps.build_runtime`. Pipelines/api **не знают** про backend — работают только с `ModelBundle.predict_proba`.

Расширение Protocol — `reload(kind, version=None) -> ReloadResult`. Используется `/admin/reload-model` для hot-swap без рестарта.

### 4. Pickle-совместимость FraudMLP (критическая гоча)

PyTorch чекпоинты содержат pickle-ссылки на `trainer.preprocess.Preprocessor` (так пакет назывался при обучении). У нас на бэке нет пакета `trainer`. Решение в `app/ml/loader.py`:

```python
def _alias_trainer(pkg):
    sys.modules["trainer"] = pkg
    sys.modules["trainer.preprocess"] = pkg.preprocess
    ...
```

Перед каждым `torch.load` мы регистрируем `app.ml._pkg_mobile` или `app.ml._pkg_web` под именем `trainer`. **`_pkg_mobile/` и `_pkg_web/` — точные копии оригинальных trainer-пакетов**, поэтому:

- Если в ML-проекте поменялась структура `Preprocessor` или добавилась колонка → **нужно перекопировать** соответствующий `_pkg_*/` (через `scripts/copy_models.py` или вручную из `../AntiFraudML*/trainer/`).
- Mobile и Web имеют **разные** наборы колонок (см. `trainer/preprocess.py`). Не пытаться объединить.
- `_LOAD_LOCK` в loader защищает от race condition при параллельной загрузке двух моделей.
- `MlflowLoader` тоже использует `_load_bundle` + `_pkg_*` — он скачивает checkpoint artifact и кормит в тот же путь. Не дублировать decoding-логику.

### 5. Cold-start клиента (нет в `customer_features.parquet`)

Модели обучены с `agg_dropout` — отсутствие истории даёт `has_history=0` и нули в агрегатах, inference корректный. **Не падать** если parquet нет; в `customer_history.maybe_load` возвращается `None`, в `predict_proba(event, agg_df=None)` тоже валидно.

### 6. Скор `0..10` маппится из весов через `WEIGHT_TO_SCORE = 2.0`

В `core/scoring.py`: `score = clamp(total_weight × 2.0, 0, 10)`. Это значит одно критичное правило (вес 2.0) уже даёт скор 4.0 (decision = `review`). Подкручивать веса в `pipelines/*/rules.py`, не множитель.

### 7. Event sink — fire-and-forget, не часть hot path'а

После `score_behavior(...)` в `app/api/behavior.py` вызывается `event_sink.enqueue(payload, kind)` в `try/except`. Падение FS, недоступность очереди, что угодно — **не должно** валить response. SLA p95 < 900мс важнее, чем гарантированная запись каждого события. Партиция может пропасть — trainer перетренируется на следующий день.

Sink — асинхронный (`app/persistence/event_sink.py:EventSink`): batch buffer в памяти, flush при `EVENT_SINK_BATCH_SIZE` или `EVENT_SINK_FLUSH_SECS` секундах. Atomic write через `.tmp` + `os.replace`. Запускается в `lifespan` через `await sink.start()`, останавливается через `await sink.stop()` (с дренажом буфера).

### 8. Per-kind `customer_features` history

`app.state.history_web` и `app.state.history_mobile` — независимые. Обновляются только при reload соответствующей модели через `/admin/reload-model`. Согласовано с тем, что MLFlow логирует customer_features как **per-model** artifact в `trainer/train.py:_Tracker.log_pyfunc`. Старое поле `app.state.history` сохранено для backward compat — fallback если per-kind не установлен.

В `app/api/behavior.py` выбор history по `is_web_payload(payload)`. Не пытаться объединить histories — у web и mobile разные FEATURE_COLUMNS (48 vs 40).

### 9. `contracts/` — единый источник правды backend ↔ trainer

`contracts/event_schema_{web,mobile}.py` и `contracts/labels_schema.py` — pandera `DataFrameSchema`. Источник: `trainer/preprocess.py` обоих ML-репо. Используются:

- В `app/persistence/event_sink.py:_coverage` — лог процента заполненности полей при flush (best-effort, todo.md #6).
- В `app/api/admin.py:labels_batch` — жёсткая валидация (400 при нарушении).
- На ML-стороне после `bash scripts/sync_contracts.sh` копирования — для валидации партиций в `trainer/extract.py`.

`strict=False` + все колонки `required=False, nullable=True` для events → unknown поля проходят, фронт может слать что есть. `labels_schema.py` — наоборот, `strict=True`.

## Конвенции разработки

### TDD обязателен

Каждое новое правило / regex / endpoint начинается с теста:

```bash
source .venv/bin/activate
python -m pytest tests/test_<your>.py::test_<case> -v   # должен упасть
# реализация
python -m pytest tests/test_<your>.py::test_<case> -v   # должен пройти
python -m pytest -q                                      # full sweep, ничего не сломали
```

92+ существующих тестов — проверяй регрессии перед коммитом.

### Где что добавлять

| Хочешь | Куда |
|---|---|
| Новое правило поведения | `app/pipelines/behavior/rules.py` (добавь функцию + кортеж `_RULES`) + тест в `tests/test_rules_behavior.py` |
| Новый regex для chat | `app/pipelines/chat/patterns.py: PHISHING_PATTERNS` + тест в `tests/test_chat_regex.py` |
| Новый сигнал по магазину | `app/pipelines/merchant/rules.py: evaluate_merchant` + тест в `tests/test_endpoint_merchant.py` |
| Новый порог/настройка | `app/config.py: Settings` (env-переопределяемая) + дефолт в `.env.example` |
| Новое поле в ScoreResponse | `app/schemas/common.py` — но тогда **обнови все 3 orchestrator-а** |
| Тестовый магазин для demo | `merchant_mock/seed.json` |
| Новое поле в event-схему | **сначала** `contracts/event_schema_*.py` (одно место правды), **потом** `bash scripts/sync_contracts.sh` копирует в ML-репо |
| Новый admin endpoint | `app/api/admin.py` под `Depends(require_admin_token)` + тест c `Authorization: Bearer test-admin-token` (`tests/conftest.py:os.environ`) |

### Что НЕ делать

- Не добавлять обязательные поля в `_BaseEvent` (`schemas/behavior.py`) — payload может приходить с любым подмножеством task.md полей. Используем `extra="allow"`. Если нужна строгая валидация — это в `contracts/`, а не в pydantic.
- Не вызывать `torch.load` в pipeline-коде — только в `LocalFileLoader._load_bundle`. `MlflowLoader` тоже использует именно эту функцию.
- Не звать LLM напрямую через httpx из orchestrator — использовать `LLMClient` Protocol для DI override в тестах.
- Не логировать содержимое сообщений или PII в structured logs. Coverage logging в event_sink логирует **только проценты заполненности**, не значения.
- Не менять `WEIGHT_TO_SCORE` (см. выше) — настраивай веса конкретных правил.
- Не блокировать `/score/*` endpoint event_sink-ом. Любое исключение от sink → `try/except` + лог.
- Не реализовывать reload модели рестартом процесса. Используй `/admin/reload-model` или extend `ModelLoader.reload()`.
- Не хардкодить пути `~/fraud/*` — читать из `settings.fraud_root`.

## Окружение и зависимости

- **Python 3.11+** на бэке (Docker — 3.12). На ML-проектах 3.13/3.14 — pickle совместим, проверено.
- **CPU PyTorch** (`--index-url https://download.pytorch.org/whl/cpu`). GPU не нужен — модели крошечные.
- **Ollama** ставится отдельным сервисом в docker-compose. Один раз: `docker compose exec ollama ollama pull qwen2.5:3b-instruct`.
- **MLFlow** + **Pandera** идут в основных deps (`pyproject.toml`). MLFlow используется только при `FRAUD_MODEL_BACKEND=mlflow`.

## Env vars (новые поверх стандартных)

```bash
FRAUD_ROOT=~/fraud                         # корень для events/labels/mlruns
FRAUD_MODEL_BACKEND=local                  # local | mlflow
MLFLOW_TRACKING_URI=file://~/fraud/mlruns  # читается только при backend=mlflow
FRAUD_BACKEND_RELOAD_TOKEN=<secret>        # обязателен для /admin/*; без него 503
EVENT_SINK_BATCH_SIZE=1000
EVENT_SINK_FLUSH_SECS=60
EVENT_SINK_ENABLED=true                    # для тестов: false
```

В `tests/conftest.py` подставляется `FRAUD_BACKEND_RELOAD_TOKEN=test-admin-token` и `EVENT_SINK_ENABLED=false` для гермитичности.

## Команды

```bash
# Полный прогон тестов
source .venv/bin/activate && pytest -v

# Поднять весь стек
docker compose up --build

# Бенчмарк против поднятого backend
python scripts/benchmark.py --base http://localhost:8000 --n 200

# Синхронизировать contracts/ в ML-репо (после изменений)
bash scripts/sync_contracts.sh

# Триггер reload модели вручную (имитация daily_flow.notify_backend)
curl -X POST http://localhost:8000/admin/reload-model \
  -H "Authorization: Bearer $FRAUD_BACKEND_RELOAD_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model_name": "fraud_mlp_web"}'
```

## SLA

p95 latency **< 900 мс** на каждом endpoint. Проверяется в `tests/test_latency.py` (LLM моканы для детерминированного замера) и в `scripts/benchmark.py` (реальный стек). При нарушении — сначала проверить fail-fast пороги, потом подумать о batch-инференсе. Event sink fire-and-forget — не должен попадать в latency.

## Связанные документы

- Внешний контракт: `README.md`
- Что осталось сделать: `todo.md`
- Schema gap трек: `update.md`
- Исходное ТЗ: `task.md`
- ML-проекты: `../AntiFraudMLMobile/CLAUDE.md`, `../AntiFraudMLWeb/CLAUDE.md`

# AntiFraud Backend

Бэкенд поведенческой антифрод-защиты. Принимает события и возвращает скор фрода `0..10` плюс рекомендуемое действие (`safe` / `review` / `sms` / `biometry`).

## Сценарии

| Endpoint | Pipeline |
|---|---|
| `POST /score/behavior` | 7 правил → **если сработали** → fail-fast (без ML) → иначе PyTorch FraudMLP |
| `POST /score/chat`     | regex-фильтр + сигналы из `counterparty_metadata` → если триггер → локальная LLM (Ollama) |
| `POST /score/merchant` | `GET merchant_mock/{site}` → правила (домен, отзывы, ИНН) → LLM по карточке + отзывам |
| `POST /admin/reload-model` | Bearer-auth swap активной модели (и `customer_features`) — для daily-retrain pipeline'а |
| `POST /admin/labels-batch` | Bearer-auth приёмник ручных лейблов от операторов → parquet в `~/fraud/labels{,_mobile}/` |

Архитектурное решение **«fail-fast rules → ML только для чистых случаев»** заметно снижает нагрузку на нейросеть и LLM и удерживает p95 < 1 с.

## Структура

```
app/
├── main.py               FastAPI app + lifespan (грузит модели, parquet, открывает HTTP-клиенты, запускает EventSink)
├── config.py             pydantic-settings (env) — включая FRAUD_ROOT, FRAUD_MODEL_BACKEND, MLFLOW_TRACKING_URI
├── deps.py               DI: Runtime, get_loader, get_history_{web,mobile}, get_event_sink, get_llm, get_merchant
├── api/
│   ├── behavior.py       POST /score/behavior + fire-and-forget hook в EventSink
│   ├── chat.py           POST /score/chat
│   ├── merchant.py       POST /score/merchant
│   └── admin.py          POST /admin/reload-model, POST /admin/labels-batch (Bearer auth)
├── schemas/
│   ├── common.py         ScoreResponse, ReloadModelRequest/Response, LabelRow, LabelsBatchResponse
│   └── behavior.py       MobileBehaviorEvent / WebBehaviorEvent (extra="allow")
├── pipelines/
│   ├── behavior/         rules.py (7 правил), orchestrator.py
│   ├── chat/             patterns.py (regex), filter.py, llm.py, orchestrator.py
│   └── merchant/         enrich.py (HTTP), rules.py, llm.py, orchestrator.py
├── ml/
│   ├── loader.py         ModelLoader Protocol + ReloadResult + LocalFileLoader (cache, sys.modules alias)
│   ├── mlflow_loader.py  MlflowLoader — скачивает checkpoint + customer_features из MLFlow Registry
│   ├── _pkg_mobile/      pickle-compat пакет (model.py / preprocess.py / aggregate.py)
│   ├── _pkg_web/         pickle-compat пакет
│   └── customer_history.py
├── persistence/
│   └── event_sink.py     Async batch parquet writer → ~/fraud/events{,_mobile}/dt=YYYY-MM-DD/
├── llm/
│   ├── client.py         async OllamaClient (/api/chat, format=json)
│   ├── prompts.py        системные промты (RU)
│   └── parser.py         clamp 0..10
└── core/
    ├── scoring.py        weights→score, decision, combine_rules_and_ml
    └── logging.py        structlog JSON

contracts/                Pandera DataFrameSchema, единый источник правды backend ↔ trainer
├── event_schema_web.py   66 полей, strict=False (best-effort)
├── event_schema_mobile.py 67 полей, strict=False (best-effort)
└── labels_schema.py      strict: customer_id, event_id, target∈{0,1}, label_dttm, source

merchant_mock/            отдельный FastAPI :9000, GET /merchant/{site} из seed.json
models/                   копии .pt / customer_features.parquet (gitignored)
tests/                    pytest: 92+ тестов, p95 latency
scripts/                  copy_models.py (артефакты), benchmark.py (латенси), sync_contracts.sh (контракты в ML-репо)
```

## Быстрый старт

```bash
# 1. Скопировать готовые ML-модели из соседних ML-проектов
python scripts/copy_models.py
#   → models/mobile_best.pt, web_best.pt, customer_features.parquet (если есть)

# 2. .env
cp .env.example .env

# 3. Поднять стек (api + ollama + merchant_mock)
docker compose up --build

# 4. Один раз — скачать LLM-модель в Ollama
docker compose exec ollama ollama pull qwen2.5:3b-instruct

# 5. Smoke-тесты
curl -X POST http://localhost:8000/score/merchant \
  -H 'content-type: application/json' \
  -d @tests/fixtures/merchant_fraud.json

curl -X POST http://localhost:8000/score/behavior \
  -H 'content-type: application/json' \
  -d @tests/fixtures/behavior_mobile_fraud.json

curl -X POST http://localhost:8000/score/chat \
  -H 'content-type: application/json' \
  -d @tests/fixtures/chat_phishing.json
```

## Локальная разработка и тесты

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --index-url https://download.pytorch.org/whl/cpu torch
pip install -e ".[dev]"

pytest -v
# → 92+ тестов, включая latency-проверку p95 < 900 мс
```

## Latency-бенчмарк против поднятого backend

```bash
python scripts/benchmark.py --base http://localhost:8000 --n 200
# behavior: p50= 42ms p95=120ms p99=180ms
# chat:     p50= 38ms p95=110ms p99=170ms
# merchant: p50= 45ms p95=130ms p99=210ms
```

## Контракт ответа `/score/*`

```json
{
  "score": 7.4,
  "decision": "sms",
  "reasons": [
    "rule:vpn_proxy",
    "rule:new_device",
    "ml:p_fraud=0.62"
  ],
  "used_model": true,
  "latency_ms": 47
}
```

`decision` маппится из `score`:
- `< 3.0` → `safe`
- `< 6.0` → `review`
- `< 8.0` → `sms`
- `≥ 8.0` → `biometry`

## Admin API (для daily-retrain pipeline)

Оба endpoint'а требуют заголовок `Authorization: Bearer $FRAUD_BACKEND_RELOAD_TOKEN`.

### `POST /admin/reload-model`

Свопает активную модель (и parquet истории) без рестарта процесса. Вызывается из `notify_backend` фазы `daily_flow` (`../AntiFraudML{Web,Mobile}/orchestration/`).

```json
// request
{"model_name": "fraud_mlp_web", "version": null}    // null → Production stage
// response
{"reloaded": true, "model_name": "fraud_mlp_web", "version": 12, "previous_version": 11}
```

Откат — тот же endpoint с явной `version=N-1`. При недоступном MLFlow Registry → `503`, активная модель остаётся прежней.

### `POST /admin/labels-batch`

Пишет ручные лейблы от операторов в `~/fraud/labels/dt=<today>/part-manual-*.parquet` (web) или `labels_mobile/...` (mobile). Schema валидируется через `contracts.labels_schema`.

```json
// request
[
  {"customer_id": 1, "event_id": 11, "target": 1, "kind": "web"},
  {"customer_id": 2, "event_id": 22, "target": 0, "kind": "mobile"}
]
// response
{"written": 2, "paths": ["/.../labels/dt=2026-05-12/part-...parquet", "/.../labels_mobile/..."]}
```

## Event sink (daily-retrain pipeline)

После успешного `/score/behavior` payload **fire-and-forget** пишется в `~/fraud/events/dt=YYYY-MM-DD/` (web) или `~/fraud/events_mobile/...` (mobile). Батч флашится по `EVENT_SINK_BATCH_SIZE=1000` событий или `EVENT_SINK_FLUSH_SECS=60`, какое раньше. Падение FS не валит endpoint — только лог.

Этот sink — источник партиций для `daily_flow` в `../AntiFraudML{Web,Mobile}/`.

## Переключатель ML backend'а

```bash
# Файловый (по умолчанию) — грузит из ./models/*.pt
FRAUD_MODEL_BACKEND=local

# MLFlow Registry — тянет models:/fraud_mlp_{web,mobile}/Production
FRAUD_MODEL_BACKEND=mlflow
MLFLOW_TRACKING_URI=file:///Users/$USER/fraud/mlruns
```

См. `app/ml/mlflow_loader.py:MlflowLoader` — скачивает checkpoint + customer_features artifact через `MlflowClient.download_artifacts` и кормит в существующий `_load_bundle()` (через alias `trainer.*`).

## Что ещё внутри

- **Совместимость pickle для FraudMLP**: pickle хранит ссылку на `trainer.preprocess.Preprocessor`, поэтому `app/ml/_pkg_mobile/` и `_pkg_web/` — точные копии trainer-пакетов из соседних ML-проектов; `loader.py` регистрирует их в `sys.modules['trainer']` перед `torch.load`.
- **Per-kind customer_features**: в `app.state` теперь `history_web` и `history_mobile` — обновляются независимо при reload соответствующей модели. Это согласовано с тем, что MLFlow логирует customer_features как artifact per-model в `trainer/train.py:_Tracker.log_pyfunc`.
- **Cold-start клиентов**: модели обучены с `agg_dropout`, поэтому отсутствие `customer_features.parquet` не ломает inference (`has_history=0`).
- **Coverage logging**: на каждом flush event_sink логирует процент заполненности всех полей из `contracts/event_schema_*.py`. См. `app/persistence/event_sink.py:_coverage`.
- **Contracts как единый источник правды**: `contracts/` копируется в `../AntiFraudML{Web,Mobile}/contracts/` скриптом `scripts/sync_contracts.sh` — trainer на ML-стороне импортирует тот же `EVENT_SCHEMA_*` для валидации партиций.

## Связанные документы

- `CLAUDE.md` — конвенции и архитектурные гочи для будущих сессий
- `todo.md` — что осталось сделать для интеграции с daily-retrain
- `update.md` — отдельный трек по schema gap backend ↔ trainer
- `task.md` — исходное ТЗ
- ML-репо: `../AntiFraudMLMobile/CLAUDE.md`, `../AntiFraudMLWeb/CLAUDE.md`

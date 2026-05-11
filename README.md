# AntiFraud Backend

Бэкенд поведенческой антифрод-защиты. Принимает события и возвращает скор фрода `0..10` плюс рекомендуемое действие (`safe` / `review` / `sms` / `biometry`).

## Сценарии

| Endpoint | Pipeline |
|---|---|
| `POST /score/behavior` | 7 правил → **если сработали** → fail-fast (без ML) → иначе PyTorch FraudMLP |
| `POST /score/chat`     | regex-фильтр + сигналы из `counterparty_metadata` → если триггер → локальная LLM (Ollama) |
| `POST /score/merchant` | `GET merchant_mock/{site}` → правила (домен, отзывы, ИНН) → LLM по карточке + отзывам |

Архитектурное решение **«fail-fast rules → ML только для чистых случаев»** заметно снижает нагрузку на нейросеть и LLM и удерживает p95 < 1 с.

## Структура

```
app/
├── main.py               FastAPI app + lifespan (грузит модели, parquet, открывает HTTP-клиенты)
├── config.py             pydantic-settings (env)
├── deps.py               DI: Runtime, get_loader, get_history, get_llm, get_merchant
├── api/
│   ├── behavior.py       POST /score/behavior
│   ├── chat.py           POST /score/chat
│   └── merchant.py       POST /score/merchant
├── schemas/
│   ├── common.py         ScoreResponse {score, decision, reasons[], used_model, latency_ms}
│   └── behavior.py       MobileBehaviorEvent / WebBehaviorEvent (extra="allow")
├── pipelines/
│   ├── behavior/         rules.py (7 правил), orchestrator.py
│   ├── chat/             patterns.py (regex), filter.py, llm.py, orchestrator.py
│   └── merchant/         enrich.py (HTTP), rules.py, llm.py, orchestrator.py
├── ml/
│   ├── loader.py         ModelLoader Protocol + LocalFileLoader (cache, sys.modules alias)
│   ├── _pkg_mobile/      pickle-compat пакет (model.py / preprocess.py / aggregate.py)
│   ├── _pkg_web/         pickle-compat пакет
│   └── customer_history.py
├── llm/
│   ├── client.py         async OllamaClient (/api/chat, format=json)
│   ├── prompts.py        системные промты (RU)
│   └── parser.py         clamp 0..10
└── core/
    ├── scoring.py        weights→score, decision, combine_rules_and_ml
    └── logging.py        structlog JSON

merchant_mock/            отдельный FastAPI :9000, GET /merchant/{site} из seed.json
models/                   копии .pt / customer_features.parquet (gitignored)
tests/                    pytest: 60+ тестов, p95 latency
scripts/                  copy_models.py (артефакты), benchmark.py (латенси)
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
# → 60+ тестов, включая latency-проверку p95 < 900 мс
```

## Latency-бенчмарк против поднятого backend

```bash
python scripts/benchmark.py --base http://localhost:8000 --n 200
# behavior: p50= 42ms p95=120ms p99=180ms
# chat:     p50= 38ms p95=110ms p99=170ms
# merchant: p50= 45ms p95=130ms p99=210ms
```

## Контракт ответа

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

## Что ещё внутри

- **Совместимость pickle для FraudMLP**: pickle хранит ссылку на `trainer.preprocess.Preprocessor`, поэтому `app/ml/_pkg_mobile/` и `_pkg_web/` — точные копии trainer-пакетов из соседних ML-проектов; `loader.py` регистрирует их в `sys.modules['trainer']` перед `torch.load`.
- **MLflow-готовность**: `ModelLoader` — Protocol, `LocalFileLoader` сейчас читает файлы. Подмена на `MlflowLoader` не требует правок в pipelines/api.
- **Cold-start клиентов**: модели обучены с `agg_dropout`, поэтому отсутствие `customer_features.parquet` не ломает inference (`has_history=0`).

См. полный план в `/Users/aleksandr/.claude/plans/scalable-mixing-walrus.md`.

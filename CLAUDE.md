# CLAUDE.md — гайд для будущих сессий

Антифрод-backend на FastAPI с тремя независимыми скоринг-pipeline'ами. Документ описывает то, что **невозможно прочитать из кода**: архитектурные решения, гочи и конвенции.

## Что это

Backend получает события и возвращает банку **скор фрода 0..10** + рекомендуемый `decision` (`safe`/`review`/`sms`/`biometry`).

| Endpoint | Pipeline |
|---|---|
| `POST /score/behavior` | 7 правил → fail-fast → PyTorch FraudMLP |
| `POST /score/chat`     | regex + meta-сигналы → если триггер → LLM (Ollama) |
| `POST /score/merchant` | GET к merchant_mock → правила → LLM по карточке + отзывам |

ML-модели **не обучаются здесь** — только инференс. Обучение в соседних проектах `../AntiFraudMLMobile/` и `../AntiFraudMLWeb/`.

## Архитектурные решения (НЕ менять без обсуждения)

### 1. Fail-fast: rules → ML только для чистых

Если `apply_rules(event)` дал суммарный вес `≥ RULE_THRESHOLD_BEHAVIOR` → возвращаем чисто rule-скор без вызова нейронки. Логика: критичные сигналы (VPN+гео-телепорт+root) уже сами по себе доказательны, нейронка только удлинит latency. Нейронка ловит **тонкие** аномалии, когда правила чисты.

То же для chat (rules-сумма ≥ threshold → зовём LLM, иначе только rules) и merchant (правила сработали ИЛИ домен молодой → LLM).

### 2. Загрузка моделей при старте, singleton в `app.state`

`create_app(load_models=True)` грузит `mobile_best.pt` и `web_best.pt` в lifespan — один раз, держим в памяти. **Никогда** не грузить модель в хендлере. Для тестов без моделей: `create_app(load_models=False)`.

### 3. `ModelLoader` — Protocol, не класс

Сейчас `LocalFileLoader` читает `.pt` с диска. Когда подключится MLflow — добавится `MlflowLoader` без правок в `pipelines/api`. **Не хардкодить** `LocalFileLoader` в pipeline-коде, использовать DI через `app.deps.get_loader`.

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
- Mobile и Web имеют **разные** `NUMERIC_COLS` (36 vs 33) и `CATEGORICAL_COLS` (27 vs 20). Не пытаться объединить.
- `_LOAD_LOCK` в loader защищает от race condition при параллельной загрузке двух моделей.

### 5. Cold-start клиента (нет в `customer_features.parquet`)

Модели обучены с `agg_dropout` — отсутствие истории даёт `has_history=0` и нули в агрегатах, inference корректный. **Не падать** если parquet нет; в `customer_history.maybe_load` возвращается `None`, в `predict_proba(event, agg_df=None)` тоже валидно.

### 6. Скор `0..10` маппится из весов через `WEIGHT_TO_SCORE = 2.0`

В `core/scoring.py`: `score = clamp(total_weight × 2.0, 0, 10)`. Это значит одно критичное правило (вес 2.0) уже даёт скор 4.0 (decision = `review`). Подкручивать веса в `pipelines/*/rules.py`, не множитель.

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

61+ существующих тестов — проверяй регрессии перед коммитом.

### Где что добавлять

| Хочешь | Куда |
|---|---|
| Новое правило поведения | `app/pipelines/behavior/rules.py` (добавь функцию + кортеж `_RULES`) + тест в `tests/test_rules_behavior.py` |
| Новый regex для chat | `app/pipelines/chat/patterns.py: PHISHING_PATTERNS` + тест в `tests/test_chat_regex.py` |
| Новый сигнал по магазину | `app/pipelines/merchant/rules.py: evaluate_merchant` + тест в `tests/test_endpoint_merchant.py` |
| Новый порог/настройка | `app/config.py: Settings` (env-переопределяемая) + дефолт в `.env.example` |
| Новое поле в ScoreResponse | `app/schemas/common.py` — но тогда **обнови все 3 orchestrator-а** |
| Тестовый магазин для demo | `merchant_mock/seed.json` |

### Что НЕ делать

- Не добавлять обязательные поля в `_BaseEvent` (`schemas/behavior.py`) — payload может приходить с любым подмножеством task.md полей. Используем `extra="allow"`.
- Не вызывать `torch.load` в pipeline-коде — только в `LocalFileLoader._load_bundle`.
- Не звать LLM напрямую через httpx из orchestrator — использовать `LLMClient` Protocol для DI override в тестах.
- Не логировать содержимое сообщений или PII в structured logs.
- Не менять `WEIGHT_TO_SCORE` (см. выше) — настраивай веса конкретных правил.

## Окружение и зависимости

- **Python 3.11+** на бэке (Docker — 3.12). На ML-проектах 3.13/3.14 — pickle совместим, проверено.
- **CPU PyTorch** (`--index-url https://download.pytorch.org/whl/cpu`). GPU не нужен — модели крошечные.
- **Ollama** ставится отдельным сервисом в docker-compose. Один раз: `docker compose exec ollama ollama pull qwen2.5:3b-instruct`.

## Команды

```bash
# Полный прогон тестов
source .venv/bin/activate && pytest -v

# Поднять весь стек
docker compose up --build

# Бенчмарк против поднятого backend
python scripts/benchmark.py --base http://localhost:8000 --n 200
```

## SLA

p95 latency **< 900 мс** на каждом endpoint. Проверяется в `tests/test_latency.py` (LLM моканы для детерминированного замера) и в `scripts/benchmark.py` (реальный стек). При нарушении — сначала проверить fail-fast пороги, потом подумать о batch-инференсе.

## Связанные документы

- План реализации: `/Users/aleksandr/.claude/plans/scalable-mixing-walrus.md`
- Внешний контракт: `README.md`
- Исходное ТЗ: `task.md`
- ML-проекты: `../AntiFraudMLMobile/CLAUDE.md`, `../AntiFraudMLWeb/CLAUDE.md`

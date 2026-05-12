# AntiFraudMain — TODO для интеграции с retrain pipeline

Что есть сейчас и что нужно дописать, чтобы AntiFraudMLWeb +
AntiFraudMLMobile могли работать в полном daily-retrain цикле.

## Что готово

- **FastAPI app** (`app/main.py`) с lifespan'ом, грузит модели на старте
  через `LocalFileLoader` из `./models/{mobile,web}_best.pt`.
- **`/score/behavior`** endpoint (`app/api/behavior.py`) — discriminator
  web/mobile через `is_web_payload(payload)`, скорит через rules → ML.
- **`/score/chat`**, **`/score/merchant`**, **`/health`** — другие
  endpoint'ы, не относятся к retrain'у.
- **Pydantic schemas** (`app/schemas/behavior.py`) — 16 строгих полей +
  `extra="allow"`, payload летит в модель как dict.
- **`ModelLoader` Protocol + `LocalFileLoader`** (`app/ml/loader.py`) —
  `torch.load(.pt)`, lazy + кэш, thread-safe через `_LOAD_LOCK`. Грузит
  из FS, **не из MLFlow**.
- **`CustomerHistory.maybe_load`** (`app/ml/customer_history.py`) —
  статичный `customer_features.parquet`, путь из настроек.
- **`_pkg_web` / `_pkg_mobile`** — локальные копии trainer'овых модулей
  под alias `trainer.*`, чтобы pickle препроцессора в чекпоинте
  разрешался.
- **Тесты** (`tests/`) — endpoint, ML loader, rules, latency, chat regex.

## Что надо сделать (по приоритету)

### 1. Event sink — blocker №1 для daily_flow

Без этого daily_flow тренируется на legacy-копии `data_augmented/*`
вместо реального потока.

**Где:** новый модуль `app/persistence/event_sink.py`.

**Что:**
- Асинхронный writer (batch в памяти: max 1000 events или 60 с).
- Atomic write через `.tmp` + `os.rename`:
  - web events → `~/fraud/events/dt=YYYY-MM-DD/part-<uuid>.parquet`
  - mobile events → `~/fraud/events_mobile/dt=YYYY-MM-DD/part-<uuid>.parquet`
  - Дискриминатор по `is_web_payload(payload)`.
- Падение writer'а **не должно** ронять `/score/*` — fire-and-forget,
  ошибки только в лог.
- Хук вызывается из `app/api/behavior.py` после `score_behavior(...)`.
- Путь корня `FRAUD_ROOT` в `app/config.py` (default `~/fraud`).

**Тесты:** `tests/test_event_sink.py` — atomic write, batch flush по
size/timeout, отсутствие ошибок при недоступном FS (writer offline,
endpoint всё равно отвечает 200).

### 2. `/admin/reload-model` — blocker №2 для daily_flow

Без этого `daily_flow.notify_backend` падает после промоушена → новая
модель в Registry, но backend всё ещё на старой.

**Где:** новый `app/api/admin.py`.

**Что:**
- `POST /admin/reload-model` с Bearer auth (env
  `FRAUD_BACKEND_RELOAD_TOKEN`).
- Payload: `{"model_name": "fraud_mlp_mobile" | "fraud_mlp_web",
  "version": int | null}`. Если `version` отсутствует — тянет
  `models:/<model_name>/Production`.
- Свопает `app.state.models` без рестарта (через `LocalFileLoader`
  invalidation или `MlflowLoader` reload — см. #3).
- Возвращает `{"reloaded": true, "model_name": ..., "version": ...,
  "previous_version": ...}` для аудита.
- Откат — тот же endpoint с явной `version=N-1`.

**Тесты:** `tests/test_admin_reload.py` — auth, успешный swap, откат,
поведение при недоступном MLFlow registry.

### 3. `MlflowLoader` — production-loader вместо файлового

`LocalFileLoader` грузит из `./models/*.pt` — это не масштабируется на
ежедневные новые версии. Нужно тянуть из MLFlow Registry.

**Где:** дополнить `app/ml/loader.py`, добавить класс `MlflowLoader`
рядом с `LocalFileLoader` (тот же `ModelLoader` Protocol).

**Что:**
- `MlflowLoader.load_web()` / `.load_mobile()` тянут через
  `mlflow.pyfunc.load_model("models:/fraud_mlp_{web,mobile}/Production")`.
- `customer_features.parquet` приходит как артефакт той же версии модели
  (через `context.artifacts["customer_features"]` — уже логируется
  `trainer/train.py:_Tracker.log_pyfunc`).
- Switcher в `app/config.py`:
  - `FRAUD_MODEL_BACKEND: Literal["local", "mlflow"] = "local"`
  - `MLFLOW_TRACKING_URI: str = "file://~/fraud/mlruns"`
- В `app/deps.py:build_runtime` ветка по этой настройке.

**Тесты:** `tests/test_mlflow_loader.py` — load_web / load_mobile,
fallback при отсутствии Production-версии, версии web и mobile
**независимы** (загрузка одной не ломает другую).

### 4. Labels source integration — без этого retrain бессмыслен

Это не код в `AntiFraudMain` сам по себе, а интеграция с внешними
системами. Без неё `~/fraud/labels{,_mobile}/dt=*/` всегда пуст,
daily_flow получает только статичный `data/train_labels.parquet`.

**Варианты канала (хотя бы один):**

- **Chargeback feed от процессинга** (лаг 1-30 дней). Внешний сервис
  или cron-скрипт пишет в `~/fraud/labels/dt=YYYY-MM-DD/part-*.parquet`
  со схемой `(customer_id, event_id, target, label_dttm,
  source="chargeback")`.
- **Выгрузка решений fraud-команды из CRM** (CSV экспорт → parquet
  converter). Аналогичная схема, `source="fraud_team"`.
- **Customer complaints** через support API. `source="complaint"`.
- **Ручные отметки операторов** через админ-эндпоинт:
  - Новый `app/api/admin.py:POST /admin/labels-batch` принимает массив
    `(customer_id, event_id, target)` от оператора, пишет в
    `~/fraud/labels{,_mobile}/dt=<today>/part-manual-<uuid>.parquet`.

**Где живёт код:** скорее всего отдельный сервис рядом с FastAPI
(`scripts/chargeback_ingest.py` cron). Backend нужен только для (4d)
admin labels endpoint.

### 5. Pandera schema contract — единый контракт backend ↔ trainer

Сейчас `extra="allow"` пропускает любой payload, trainer на retrain'е
получает kakofony схем между партициями.

**Где:** новый `contracts/` каталог в `AntiFraudMain/`:
- `contracts/event_schema_web.py` — Pandera `DataFrameSchema` для web.
- `contracts/event_schema_mobile.py` — для mobile.

**Что:**
- Типы + nullable + value ranges для всех 71 (web) / 74 (mobile) полей.
- Импортируется:
  - В `app/persistence/event_sink.py` — валидация перед записью
    (нарушения → лог, не падение).
  - В `AntiFraudMLWeb/trainer/extract.py` и
    `AntiFraudMLMobile/trainer/extract.py` — проверка прочитанных
    партиций (через git submodule или copy-on-CI).

### 6. Schema gap fix — расширить pydantic с 16 до 71/74 полей

Опционально, в зависимости от готовности фронтового SDK.

**Варианты:**

- **Best-effort (рекомендую на bootstrap):** оставить `extra="allow"`,
  фронт шлёт что есть, trainer работает на пересечении полей. Drift
  drift'ом, но pipeline не падает. Логировать coverage по полям.
- **Strict:** жёстко описать все 71/74 поля в pydantic. Хрупко,
  требует frontend SDK readiness; фронт обязан слать всё. На bootstrap'е
  откатываемся в 400 на половине запросов.

**Где:** `app/schemas/behavior.py:WebBehaviorEvent` / `MobileBehaviorEvent`.

### 7. (Опционально) Cross-repo customer_id namespace

Не блокер, но решит проблему коллизий между synthetic-датасетом
(`customer_id` = int 1..100000) и production-клиентами банка (UUID
или другое пространство).

**Где:** `app/schemas/behavior.py:17` и `app/api/behavior.py`.

**Что:** валидация `customer_id: str = Field(..., pattern=r"^(bank|synth):.+")`
ИЛИ auto-prefix в API layer перед передачей в model + event_sink.

Подробности в основной беседе — обсуждалось как вариант 2 (option 1 —
зачистить `customer_features.parquet` на go-live — проще и быстрее).

## Что НЕ надо делать в backend

- `daily_flow` / orchestration — это в training-репо
  (`AntiFraudML{Web,Mobile}/orchestration/`).
- `feature_generator` — dev/CI only, в backend не идёт.
- MLFlow tracking server — это в training-репо.

## Минимальный путь к рабочему retrain'у

**#1 + #2 + #3.** Без них daily_flow умеет тренироваться, но не
получает реальных событий и не может сообщить backend'у о новой модели.

**#4 (labels) и #5 (contracts) — следующая волна.** Без #4 retrain
тренирует ту же модель на тех же данных каждый день; без #5 нет
гарантии что схемы партиций согласованы между training-репо.

**#6 и #7 — отдельные тики**, можно делать параллельно с основным
путём.

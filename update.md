# Update — Schema gap между backend и trainer'ом

> **NB:** оперативный список того, что в backend'е сделано и что нужно
> для интеграции с retrain pipeline — в `todo.md`. Этот файл — конспект
> по отдельному треку schema gap'а.

Конспект отдельного трека: рассинхрон схем между тем, что валидирует
`AntiFraudMain`, и тем, что ждёт `AntiFraudMLWeb/trainer` и
`AntiFraudMLMobile/trainer` для обучения.

---

## Статус: best-effort реализован, strict отложен

Решение из секции 4 («best-effort на bootstrap, мигрируем на гибрид
позже») **реализовано**. Подробности в секциях 7–8.

---

## 1. Текущее состояние

### 1.1 Что валидирует backend

`app/schemas/behavior.py` описывает события через `pydantic.BaseModel` с
`model_config = ConfigDict(extra="allow")`.

**`_BaseEvent`** (общая часть, 10 полей):

```
customer_id, event_id, event_dttm, operaton_amt, hour_of_day,
day_of_week, is_vpn_detected, is_proxy_detected, geo_speed_km_h,
session_duration_sec, transfers_count_last_10min
```

**`WebBehaviorEvent`** добавляет 5 полей:

```
browser_fingerprint, user_agent, is_tor_detected, is_new_browser,
is_new_device
```

**`MobileBehaviorEvent`** добавляет 3 поля:

```
os_type, device_id, is_new_device
```

Итого web-payload **строго** валидирует **16 полей** в pydantic, всё
остальное проходит через `extra="allow"` и доступно как ключи словаря
без типизации, диапазонной проверки, defaults.

### 1.2 Что ждёт trainer (canonical)

Источник правды теперь — `contracts/event_schema_{web,mobile}.py`
(см. секцию 7). Списки колонок зеркалят `trainer/preprocess.py` обоих
ML-репо:

- **Web (66 полей):** 3 identity + 44 numeric + 19 categorical.
- **Mobile (67 полей):** 3 identity + 37 numeric + 27 categorical.

Подробности — `AntiFraudMLWeb/trainer/preprocess.py:17–69` и
`AntiFraudMLMobile/trainer/preprocess.py:17–75`.

## 2. Где зияет дыра

Pydantic-схема валидирует 16 полей, contracts/canonical — 66/67. Дельта
~50 полей делится на категории по тому, **кто** может их заполнить.

### 2.1 Биометрика взаимодействия (~12 полей)

```
mouse_velocity_avg, mouse_acceleration_avg, mouse_jitter_score,
mouse_linearity_score, click_duration_avg_ms, right_click_count,
scroll_velocity_avg, double_click_count,
keyboard_typing_speed_median_ms, keyboard_typing_speed_std_dev,
keyboard_typing_rhythm_cv, drag_drop_events
```

Эти величины может посчитать только **фронтовый SDK**, накапливающий
DOM-события `mousemove` / `keydown` за сессию.

### 2.2 Fingerprinting (~5 полей)

```
canvas_fingerprint, audio_fingerprint, webgl_vendor,
screen_color_depth, installed_fonts_count
```

Каноническая fingerprinting-задача — JS на клиенте (FingerprintJS /
`<canvas>` rendering hash / `AudioContext` fingerprint). Backend не
получит без явной отправки.

### 2.3 Form / clipboard поведение (~13 полей)

```
backspace_ratio, clipboard_paste_ratio, copy_events_count,
paste_events_count, tab_switch_count, focus_blur_count,
form_fill_duration_sec, idle_time_before_submit_sec,
error_correction_ratio, hover_time_avg_ms, resize_events_count,
zoom_level, pages_visited_count
```

Тоже фронтовая зона — DOM-события формы.

### 2.4 Network / device (~10 полей)

```
ip_address_hash, connection_type, network_rtt_avg_ms, asn,
isp_name, screen_resolution, system_language, browser_language,
accept_language, timezone
```

Эти **может дополнить сам backend** из HTTP-заголовков и IP-геобазы:
`Accept-Language`, `User-Agent`, ASN/ISP из MaxMind/IPinfo, RTT из
TCP-метрик. Кандидаты на enrichment-пакет.

### 2.5 Browser identity (~4 поля)

```
browser_name, browser_version, os_type, os_version
```

Парсится из `User-Agent` (через `ua-parser` или `user_agents`). Сейчас
приходит сырой `user_agent` — но trainer ждёт уже разобранные
категории.

### 2.6 Login / trust (~5 полей)

```
login_method, failed_login_attempts, time_since_last_login_sec,
device_trust_score, timezone_offset
```

Backend знает это сам (auth-state, история сессий клиента) — но в
payload событий `/score/behavior` не прокидывает.

### 2.7 Transaction enrichment (~6 полей)

```
currency_iso_cd, mcc_code, pos_cd, merchant_name, transaction_type,
session_id
```

Должны приходить из транзакционной системы вместе с событием — сейчас
не валидируются.

## 3. Опции решения

### 3.1 Strict — расширить Pydantic-модель до полного набора

`WebBehaviorEvent` / `MobileBehaviorEvent` со всеми 66/67 полями,
`extra="forbid"`. Запросы без обязательных полей — HTTP 422.

**Pros:** контракт жёсткий, schema-drift невозможен.

**Cons:** требует, чтобы фронт сначала **внедрил SDK сбора биометрики/
fingerprinting** (отдельный трек, недели работы), иначе все запросы
красные. Backend перестаёт работать до полной готовности фронта.

### 3.2 Best-effort — принимать всё, дополнять, обучать на пересечении ✅

`WebBehaviorEvent` остаётся минимальным (`extra="allow"`), backend
**обогащает** payload тем, что может вытащить сам.

EventSink пишет в parquet **всё, что есть** (включая NaN на
отсутствующих биометриках). Trainer работает на пересечении: NaN → 0 в
`Preprocessor.transform_events` (уже умеет).

**Pros:** не блокирует ни фронт, ни backend; постепенный rollout фич.

**Cons:** модель в bootstrap-периоде учится на разреженных биометриках —
это вернёт реальное AUC к ~0.7–0.8 вместо нынешнего синтетического 1.0
(что **ожидаемо** и **правильно**).

### 3.3 Гибрид — strict на серверных полях, optional на клиентских

В Pydantic три группы:

- **Required (~30 полей):** identity, transaction, network — backend
  обязан их дополнить либо отдать 422.
- **Optional (~41 поле):** биометрика / fingerprint — `default=None`,
  trainer обрабатывает пропуски.
- Никаких `extra="allow"`; неизвестные поля → schema-drift warning.

## 4. Рекомендация

**Идём по 3.2 (best-effort), мигрируем на 3.3 (гибрид), когда фронт
накопит данные.** Реализация best-effort пути — см. секции 7–8.

Следующий шаг — после первой недели daily-train'а посмотреть coverage
(см. логи `event_sink_flush`) и переключить **те поля, которые backend
реально научился дополнять** в `required` секции 3.3.

## 5. Что НЕ делать в этом треке

- **Не трогать `WebBehaviorEvent` / `MobileBehaviorEvent` до
  одобрения архитектурного решения.** Жёсткое расширение схемы — это
  breaking change.
- **Не пытаться синхронизировать схемы вручную копи-пейстом.** Единый
  источник истины — `contracts/event_schema_*.py`, sync делается через
  `bash scripts/sync_contracts.sh` (rsync в `../AntiFraudML*/contracts/`).

## 6. Чек-лист — что сделано / осталось

- [x] **`contracts/event_schema_{web,mobile}.py`** — pandera-схемы,
      зеркалят `trainer/preprocess.py` обоих ML-репо. 66/67 полей.
- [x] **`contracts/labels_schema.py`** — для `/admin/labels-batch`,
      strict-валидация.
- [x] **`scripts/sync_contracts.sh`** — rsync в оба ML-репо.
- [x] **EventSink** (`app/persistence/event_sink.py`) — пишет всё что
      приходит, fire-and-forget. Партиции в
      `~/fraud/events{,_mobile}/dt=YYYY-MM-DD/part-*.parquet`.
- [x] **Coverage logging** при flush — лог процента заполненности
      каждого поля из `EVENT_FIELDS_*` (без значений, только статистика).
- [ ] **`app/enrich/`** — пакет UA/geo/header-enrichment'ов (отдельный
      PR, начинать когда первая итерация retrain'а пройдёт).
- [ ] **Спецификация frontend SDK** сбора биометрики (отдельный тикет).
- [ ] **Evidently-репорт** или дашборд по полноте полей (часть MLOps-плана).
- [ ] **Миграция к 3.3 (гибрид)** — после стабилизации enrichment'ов и
      появления frontend SDK.

## 7. Реализация best-effort пути (что есть прямо сейчас)

### 7.1 `contracts/` как single source of truth

Pandera-схемы лежат в `Back/contracts/` и **импортируются обоими**
сторонами:

- Backend: `from contracts import EVENT_SCHEMA_WEB, EVENT_FIELDS_WEB,
  LABELS_SCHEMA` (см. `app/persistence/event_sink.py`,
  `app/api/admin.py`).
- ML-репо: после `bash scripts/sync_contracts.sh` файлы лежат в
  `../AntiFraudMLWeb/contracts/` и `../AntiFraudMLMobile/contracts/`,
  trainer импортирует напрямую.

Схемы намеренно слабые: `strict=False`, все non-identity колонки
`required=False, nullable=True`. Это позволяет:

- Фронту слать любое подмножество полей без 422.
- Backend'у писать в parquet через event_sink что есть.
- Trainer'у получать партиции разной полноты — `Preprocessor` уже
  умеет nan → 0.

### 7.2 Coverage logging

На каждом flush event_sink логирует `coverage: dict[field, fraction]`
через structlog. Пример:

```json
{"event": "event_sink_flush", "kind": "web", "rows": 1000,
 "coverage": {"customer_id": 1.0, "browser_fingerprint": 0.42,
              "mouse_velocity_avg": 0.0, ...}}
```

Это даёт **drift visibility без жёсткой валидации**. Алертам на drop
покрытия — самое место, но это уже сторона observability stack'а.

### 7.3 Где живёт код

- `Back/contracts/__init__.py` — re-exports.
- `Back/contracts/event_schema_web.py` — 66 полей.
- `Back/contracts/event_schema_mobile.py` — 67 полей.
- `Back/contracts/labels_schema.py` — strict, для `/admin/labels-batch`.
- `Back/scripts/sync_contracts.sh` — rsync в оба ML-репо.
- `Back/app/persistence/event_sink.py:_coverage` — coverage logging.

## 8. Дальше: путь к 3.3 (гибрид)

Когда coverage по группам 2.4–2.7 (то, что backend может дополнить
сам) стабильно >95%:

1. Поднять `app/enrich/` (UA-parser, geoip, header parsing,
   session-state).
2. Перенести эти поля из best-effort в required в `WebBehaviorEvent` /
   `MobileBehaviorEvent` (pydantic).
3. Когда frontend SDK выпустит — повторить шаг 2 для биометрики.
4. Снять `extra="allow"`, оставить `extra="ignore"` для совместимости
   со старыми клиентами.

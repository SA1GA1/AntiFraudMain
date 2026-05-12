# Update — Schema gap между backend и trainer'ом

> **NB:** оперативный список того, что в backend'е сделано и что нужно
> для интеграции с retrain pipeline — в `todo.md`. Этот файл — конспект
> по отдельному треку schema gap'а.

Конспект отдельного трека, не связанного напрямую с MLOps-планом
(`AntiFraudMLWeb/update.md`). Сюда вынесена проблема рассинхрона схем
между тем, что валидирует `AntiFraudMain`, и тем, что ждёт
`AntiFraudMLWeb/trainer` для обучения.

---

## 1. Текущее состояние

### 1.1 Что валидирует backend

`app/schemas/behavior.py` описывает три типа событий через
`pydantic.BaseModel` с `model_config = ConfigDict(extra="allow")`.

**`_BaseEvent`** (общая часть, 10 полей):

```
customer_id, event_id, event_dttm, operaton_amt, hour_of_day,
day_of_week, is_vpn_detected, is_proxy_detected, geo_speed_km_h,
session_duration_sec, transfers_count_last_10min
```

**`WebBehaviorEvent` добавляет 5 полей:**

```
browser_fingerprint, user_agent, is_tor_detected, is_new_browser,
is_new_device
```

**`MobileBehaviorEvent` добавляет 3 поля:**

```
os_type, device_id, is_new_device
```

Итого web-payload **строго** валидирует **16 полей**, всё остальное
проваливается через `extra="allow"` и доступно как ключи словаря
без типизации, диапазонной проверки, defaults.

### 1.2 Что в task.md / ждёт trainer

`AntiFraudMLWeb` обучается на **71 поле** (см. `AntiFraudMLWeb/task.md` и
`AntiFraudMLWeb/CLAUDE.md` раздел «71 колонка task.md»). Из них trainer
использует:

- **19 категориальных** — `browser_name`, `browser_version`, `os_type`,
  `os_version`, `screen_resolution`, `system_language`, `browser_language`,
  `accept_language`, `merchant_name`, `transaction_type`,
  `connection_type`, `isp_name`, `webgl_vendor`, `login_method`,
  `currency_iso_cd`, `mcc_code`, `pos_cd`, `hour_of_day`, `day_of_week`.
- **44 числовых** — `operaton_amt`, флаги `is_*`, mouse/keyboard биометрия,
  click/scroll/form-метрики, network-RTT, login-trust, fingerprint-числа.

## 2. Где зияет дыра

Сравнение полей `WebBehaviorEvent` (16 валидируемых) и task.md (71) даёт
**55 полей**, которые backend сейчас не описывает в Pydantic-схеме и **с
большой вероятностью не приходят с фронта совсем**:

### 2.1 Биометрика взаимодействия (12 полей)

```
mouse_velocity_avg, mouse_acceleration_avg, mouse_jitter_score,
mouse_linearity_score, click_duration_avg_ms, right_click_count,
scroll_velocity_avg, double_click_count,
keyboard_typing_speed_median_ms, keyboard_typing_speed_std_dev,
keyboard_typing_rhythm_cv, drag_drop_events
```

Эти величины может посчитать только **фронтовый SDK**, накапливающий
DOM-события `mousemove` / `keydown` за сессию. Бэкенд их физически
не способен «дописать» — если фронт не собирает, признаков нет.

### 2.2 Fingerprinting (5 полей)

```
canvas_fingerprint, audio_fingerprint, webgl_vendor,
screen_color_depth, installed_fonts_count
```

Каноническая fingerprinting-задача — снова **JS на клиенте**
(FingerprintJS / `<canvas>` rendering hash / `AudioContext` fingerprint).
Backend не получит без явной отправки.

### 2.3 Form / clipboard поведение (13 полей)

```
backspace_ratio, clipboard_paste_ratio, copy_events_count,
paste_events_count, tab_switch_count, focus_blur_count,
form_fill_duration_sec, idle_time_before_submit_sec,
error_correction_ratio, hover_time_avg_ms, resize_events_count,
zoom_level, pages_visited_count
```

Тоже фронтовая зона — DOM-события формы.

### 2.4 Network / device (10 полей)

```
ip_address_hash, connection_type, network_rtt_avg_ms, asn,
isp_name, screen_resolution, system_language, browser_language,
accept_language, timezone
```

Эти **может дополнить сам backend** из HTTP-заголовков и IP-геобазы
без участия фронта: `Accept-Language`, `User-Agent`, ASN/ISP из
MaxMind/IPinfo, RTT из TCP-метрик, разрешение экрана — с фронта (есть
в `screen.width`).

### 2.5 Browser identity (4 поля)

```
browser_name, browser_version, os_type, os_version
```

Парсится из `User-Agent` (на бэкенде, через `ua-parser` или
`user_agents`). Сейчас приходит сырой `user_agent` — но trainer ждёт
уже разобранные категории.

### 2.6 Login / trust (5 полей)

```
login_method, failed_login_attempts, time_since_last_login_sec,
device_trust_score, timezone_offset
```

Backend знает это **сам**, потому что это его доменная логика
(auth-state, история сессий клиента) — но в payload событий
`/score/behavior` не прокидывает.

### 2.7 Transaction enrichment (6 полей)

```
currency_iso_cd, mcc_code, pos_cd, merchant_name, transaction_type,
session_id
```

Должны приходить из транзакционной системы вместе с событием —
сейчас не валидируются.

## 3. Опции решения

### 3.1 Strict — расширить Pydantic-модель до 71 поля

Превращаем `WebBehaviorEvent` в полную схему: все 71 поле, типы и
диапазоны. `extra="forbid"`. Запросы без обязательных полей —
HTTP 422.

**Pros:** контракт жёсткий, schema-drift невозможен, Pandera-валидация
в трейнере становится тривиальной (схемы совпадают), ошибки видны
сразу на клиенте.

**Cons:** требует, чтобы фронт сначала **внедрил SDK сбора биометрики/
fingerprinting** (новый трек, недели работы), иначе все запросы
красные. Backend перестаёт работать до полной готовности фронта.

### 3.2 Best-effort — принимать всё, дополнять на бэкенде, обучать на пересечении

`WebBehaviorEvent` остаётся минимальным (как сейчас), backend
**обогащает** payload тем, что может вытащить сам (3.1.4–3.1.6):
- `app/enrich/headers.py` — `accept_language`, `system_language` из заголовков.
- `app/enrich/ua.py` — `browser_name/version`, `os_type/version` из `user_agent`.
- `app/enrich/geoip.py` — `asn`, `isp_name`, `ip_address_hash` из IP.
- `app/enrich/session.py` — `login_method`, `failed_login_attempts`,
  `time_since_last_login_sec`, `device_trust_score` из internal state.

EventSink пишет в parquet **всё, что есть** (включая NaN на отсутствующих
биометриках). Trainer работает на пересечении: NaN → 0 в Preprocessor
(уже умеет).

**Pros:** не блокирует ни фронт, ни backend; постепенный rollout фич;
покрывает ~30 из 71 поля без участия фронта.

**Cons:** модель в bootstrap-периоде учится на разреженных биометриках —
это вернёт реальное AUC к ~0.7–0.8 вместо нынешнего синтетического 1.0
(что **ожидаемо** и **правильно**).

### 3.3 Гибрид — strict на серверных полях, optional на клиентских

В Pydantic делаем 3 группы:
- **Required (~30 полей):** identity, transaction, network — backend
  обязан их дополнить либо отдать 422.
- **Optional (~41 поле):** биометрика / fingerprint — `default=None`,
  trainer обрабатывает пропуски.
- Никаких `extra="allow"` — приходящие неизвестные поля логируются как
  schema-drift warning.

**Pros:** контракт частично жёсткий (сразу ловит баги в backend
enrichment-логике), но не блокирует фронт.

**Cons:** больше boilerplate Pydantic-моделей, нужна осмысленная
дискриминация «опционально, но потеря качества» vs «обязательно».

## 4. Рекомендация

**Идём по 3.2 (best-effort) во время bootstrap, мигрируем на 3.3
(гибрид) когда стабилизируется набор enrichment'ов.** Чистый strict
(3.1) бессмыслен до того момента, пока на фронте не появится SDK сбора
биометрики — а это отдельный трек.

Конкретный порядок:

1. Бэкенд начинает писать sink (см. `AntiFraudMLWeb/update.md` план) —
   с тем, что есть в payload + минимальный enrichment (UA-parser,
   `accept_language` из заголовков).
2. После первой недели daily-train'а — Evidently-отчёт по drift
   логирует «X% полей null в Y% строк», видим реальную полноту схемы.
3. Расширяем enrichment-функции, сужаем optional → required по тем
   полям, которые backend **реально** научился дополнять
   (`browser_name`, `os_type`, `asn`, `login_method`...).
4. Параллельно ставится задача frontend SDK — собирать мышь, клавиатуру,
   canvas. Когда покрытие >80% сессий — переключаем эти поля в required.

## 5. Что НЕ делать в этом треке

- **Не трогать `WebBehaviorEvent` / `MobileBehaviorEvent` до
  одобрения архитектурного решения.** Жёсткое расширение схемы — это
  breaking change для существующих интеграций.
- **Не путать с MLOps-планом** (`AntiFraudMLWeb/update.md`). Sink
  пишет «что приходит», retrain работает «на пересечении». Эти два
  трека независимы.
- **Не пытаться синхронизировать схемы вручную копи-пейстом.** Когда
  дойдёт до 3.3, единственный источник истины — Pandera-schema в
  `contracts/event_schema.py`, который импортируют обе стороны
  (backend для валидации входа, trainer для валидации parquet'а перед
  обучением).

## 6. TODO (вне этого документа)

- [ ] Спецификация frontend SDK сбора биометрики (отдельный тикет).
- [ ] `app/enrich/` — пакет UA/geo/header-enrichment'ов (отдельный PR).
- [ ] `contracts/event_schema.py` — Pandera schema, единая для обеих
      сторон (когда дойдём до 3.3).
- [ ] Evidently-репорт по полноте полей (часть MLOps-плана, но
      результат читается из этого трека).

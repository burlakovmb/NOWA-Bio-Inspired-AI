# Issue #54 — Аффективное ядро в симулированных секундах

English: [issue-54-affect-simulated-time.en.md](issue-54-affect-simulated-time.en.md)

**Часть 1 (ядро):** PR #72 — `src/…`, `tests/test_affective_time.py`.  
**Часть 2 (демо Colony):** PR #73 — `Demo/Colony chinchillas/src/colony_agent.py`, `colony_storage.py`, `tests/test_issue_54_alarm.py`, `src/swarm.py` (§7).

Код (ядро): `src/affective_space.py`, `src/agent.py`, `src/sleep.py`, `src/storage.py`, `src/genome.py`, `src/affective_persistence.py`, `src/affective_background.py`, `src/mcp_body/_compat.py`, `Demo/Virtual company/src/nowa_sandbox/training_loop.py`.

---

## 1. База времени

Удержание осей, аллостаз baseline, дрейф norm-cap, распад следов persistence и поля background считаются в **симулированных секундах** (`time_elapsed` / host `dt`), а не как «одно решение = одна секунда», если хост не передаёт `dt=1`.

По оси за одну секунду множитель удержания  
`m = clamp(axis_decay[axis] − lambda_reg, 0, 0.999)`.  
Шаг длины `dt` применяет `m ** dt` к отклонению от текущего baseline. При `dt = 1` совпадает с дискретным шагом до #54. Десять шагов по 1 с равны одному шагу 10 с (`test_one_second_steps_match_ten_second_steps`).

`apply_impulses` и `step(..., time_elapsed=0)` только добавляют импульсы: без удержания, движения baseline и norm-cap. `advance(dt)` двигает только время. Полный `step` сначала интегрирует за `dt`, затем суммирует импульсы **в конце** интервала.

---

## 2. Baseline и уставка `b0`

| Поле | Роль |
| --- | --- |
| `baseline` | Медленный аллостатический уровень |
| `baseline_setpoint` (`b0`) | Фиксированный якорь личности; копия `baseline` при создании; **нового гена нет** |

`baseline_adapt_rate` — **за симулированную секунду**. Дефолт `1/(6×3600) ≈ 4,63×10⁻⁵` (τ ≈ 6 ч к «прожитой» оси). Ген `af_baseline_adapt_rate`: диапазон `[0, 0.01]`, дефолт и сигма вдвое меньше старого пошагового (см. таблицу в [SPEC_A_GenomeVector.ru.md](../SPEC_A_GenomeVector.ru.md)).

Возврат `baseline` к `b0` с коэффициентом `0,25 × baseline_adapt_rate` (τ ≈ 24 ч). При хроническом стрессе ось и baseline выходят в равновесие, где baseline примерно на **80%** пути от `b0` к устойчивому отклонению оси (набор аллостатической нагрузки во сне не ускоряется).

---

## 3. Сон

В циклах консолидации `AffectiveSpace.step(..., asleep=True)`:

- Быстрее снимает отклонение оси к baseline и baseline к `b0` с `SLEEP_RECOVERY_SCALE = 4`.
- Берёт `time_elapsed` из `SleepManager._affective_cycle_dt()`.

`deep_sleep(cycles, sleep_duration_seconds=…)` делит суммарное симулированное время сна поровну по циклам. Без `sleep_duration_seconds` сумма `cycles × SECONDS_PER_SLEEP_CYCLE` (`1800` с). Отдельный `sleep_cycle()` — один срез `SECONDS_PER_SLEEP_CYCLE`.

---

## 4. Агент и хосты

| Путь | `time_elapsed` |
| --- | --- |
| Обычный `Agent.step` / commit | Host `dt` из `_advance_host_clock` |
| `decision_only=True` | Recall через `apply_impulses` (`0`); одно продвижение аффекта на commit с host `dt` |
| `mcp_body/_compat.apply_impulses`, импульсы VC `training_loop` | `0` |
| Обновления `AffectivePersistence` / `AffectiveBackground` из агента | Host `dt` |

---

## 5. Сохранение `.nowa`

`baseline_setpoint` пишется в блок аффекта. Без ключа при загрузке по каждой оси берётся загруженный `baseline` (`AgentStorage`, `tests/test_affective_time.py::test_setpoint_roundtrip_and_missing_field`).

**Совместимость:** Старые сохранения с `baseline_adapt_rate = 0.002` читаются как **за секунду** (τ ≈ 8 мин), не за решение.

---

## 6. Известные ограничения (ядро, часть 1)

| Элемент | Поведение |
| --- | --- |
| Тревога колонии / host `dt` | Закрыто в §7 (часть 2) |
| Социальный fallback `src/swarm.py` | Исправлено в части 2: `time_elapsed=0.0` (§7) |

---

## 7. Часть 2 — демо Colony

PR #73. Хост: `ChinchillaAgent.sim_step` в `Demo/Colony chinchillas/src/colony_agent.py`. Тесты: `Demo/Colony chinchillas/tests/test_issue_54_alarm.py`.

### 7.1 Импульсы и интеграция аффекта

| Путь | Поведение |
| --- | --- |
| `_apply_affect_impulse` | Только `affective_space.apply_impulses(inputs=…)` — **без** удержания, baseline и norm-cap. Показатели вида `stress * dt` масштабируются вызывающим кодом. |
| Бодрствующий `sim_step` | `step(…, decision_only=True, dt=host_dt)` двигает аффект один раз; `commit_executed_transition` не добавляет второй host `dt`. |
| Тик принудительного сна (без `step`) | `advance_time(host_dt)`, затем `_advance_affect_while_asleep(host_dt)`: обнуляет `time_elapsed` и `step_elapsed` в `_pending_commit_context`, затем `affective_space.advance(elapsed, asleep=True)`. В commit уходит `affective_inputs` из нулей, чтобы пробуждающая оценка не гасила сонное восстановление. |
| `deep_sleep(…, sleep_duration_seconds=0.0)` | Аффект уже продвинут раз за тик во сне; ненулевая длительность буты **удвоила бы** тот же интервал внутри `deep_sleep`. |

### 7.2 Тревога как острое событие (не `stress > 0,7`)

Константы в начале `colony_agent.py` (символы `ALARM_*`).

| Параметр | Значение | Роль |
| --- | ---: | --- |
| `ALARM_RISE_WINDOW_S` | 4,0 | Окно трассы stress для прироста |
| `ALARM_RISE_MIN` | 0,35 | Минимальный прирост для буты |
| `ALARM_REFRACTORY_S` | 15,0 | Пауза до следующей буты |
| `ALARM_CALL_AUDIBLE_S` | 2,0 | Слышимость эмиттера соседям |
| `ALARM_KNOWN_STRESS` / `ALARM_UNKNOWN_STRESS` | 0,30 / 0,15 | Базовый импульс stress (× scale) |
| `ALARM_AROUSAL` | 0,10 | Импульс arousal (× scale) |
| `ALARM_IMPULSE_INTENSITY` | 0,7 | В `apply_impulses` |
| `ALARM_SLEEP_HEARING_GAIN` | 0,35 | Слух спящего |
| `ALARM_BUFFER_AFFINITY` | 0,65 | Порог `affinity` партнёра для буфера |
| `ALARM_BUFFER_GAIN` | 0,60 | Множитель импульса при буфере |
| `ALARM_HABITUATION_RETAIN` | 0,60 | Чувствительность после буты |
| `ALARM_HABITUATION_FLOOR` | 0,30 | Нижняя чувствительность к сигнальщику |
| `ALARM_HABITUATION_TAU_S` | 120,0 | Постоянная восстановления (~2 мин тишины) |

**Эмиссия:** `_ensure_alarm_call` (через `_is_emitting_alarm`). Спящие не лают (`_alarm_call_open` сбрасывается). Нужен прирост ≥ `ALARM_RISE_MIN` за `ALARM_RISE_WINDOW_S` по `_alarm_stress_trace`; просто высокий уровень не ретриггерит. Один `event_id` на буту; рефрактер режет цепочки на частых тиках.

**Слух:** `_perceive_alarm_calls` (из `_social_step`). Сигнальщик в **той же или соседней** зоне (`is_same_or_adjacent`). Не больше **одного** импульса на пару `(слушатель, сигнальщик, event_id)` через `_alarm_heard`. Знакомый (`knowledge`) — `ALARM_KNOWN_STRESS`, чужой — `ALARM_UNKNOWN_STRESS`. Множители: `_alarm_caller_gain` (привыкание), `_alarm_social_buffer` (связанный сосед, не сигнальщик), ослабление во сне.

**Якорь при load/create:** `_anchor_alarm_stress`, чтобы высокий сохранённый stress не считался пиком в окне.

Контекст `alarm_call` по-прежнему от `affect_tone == "fearful"` у воспринятого агента, не от порога stress.

### 7.3 Сохранение колонии — `runtime.alarm`

`ColonyStorage` пишет `runtime.alarm` из `_export_alarm_state()` (`refractory_until`, `event_id`, `event_until`, `call_open`, `emit_count`, `stress_trace`, `habituation`, `heard`). При загрузке — `_restore_alarm_state` или `_anchor_alarm_stress()` без ключа (старый сейв с высоким `affect.stress` сам не лает).

### 7.4 Fallback `src/swarm.py`

`SwarmEnvironment.apply_social_signal`: если есть только `step`, вызывается с `time_elapsed=0.0` (только импульс; без дефолтной 1 с на сигнал). Проверка: `tests/test_swarm_environment.py`.

---

## 8. Известные ограничения (часть 2)

| Элемент | Статус |
| --- | --- |
| Размножение по **медленному** кортизолу | **Не реализовано** — спаривание по-прежнему на мгновенном кортизоле в `_apply_reproduction` / `ReproductiveSystem.update`. |
| Бодрствующий `commit_executed_transition` | Производная оценка аффекта **не** масштабируется host `dt`; при хроническом стрессе ось stress может сидеть **~0,78**, пока recovery и импульсы борются с commit. |
| Часы `AffectivePersistence` на тике need-sleep | `affective_persistence.update` идёт из `Agent.step`; принудительный сон без `step` — распад следов / часы на этот тик не идут. |
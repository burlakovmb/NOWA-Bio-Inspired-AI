# Issue #54 (часть 1) — Аффективное ядро в симулированных секундах

English: [issue-54-affect-simulated-time.en.md](issue-54-affect-simulated-time.en.md)

Только ядро. PR #72. Тревога колонии и подача host `dt` — часть 2 (#54).

Код: `src/affective_space.py`, `src/agent.py`, `src/sleep.py`, `src/storage.py`, `src/genome.py`, `src/affective_persistence.py`, `src/affective_background.py`, `src/mcp_body/_compat.py`, `Demo/Virtual company/src/nowa_sandbox/training_loop.py`.

Тесты: `tests/test_affective_time.py`.

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
| Социальный fallback `src/swarm.py` | `step(inputs=…)` без `time_elapsed` → дефолт **1,0** с на сигнал |
| `deep_sleep` колонии / тревоги | Демо с `sleep_duration_seconds=0.0` — часть 2 |
| Colony `test_tc05` | Заморозка `_is_emitting_alarm`, чтобы законный стресс мог пересечь порог `0,7` |
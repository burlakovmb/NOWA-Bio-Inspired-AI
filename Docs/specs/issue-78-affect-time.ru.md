# Issue #78 — инвариантность аффекта и кортизола по dt

English: [issue-78-affect-time.en.md](issue-78-affect-time.en.md)

PR #82, ветка `team/issue-78-affect-time`. Надстройка над симулированными секундами аффекта ([issue-54-affect-simulated-time.ru.md](issue-54-affect-simulated-time.ru.md)). База для старой кривой: `a2bab8f`.

Код: `src/agent.py`, `src/affective_space.py`, `src/neuromodulators.py`, `src/autonomous_organism.py`. Тесты: `tests/test_issue_78_affect_time.py`, расширен `tests/test_neuromodulators_phase2.py`. Демо (только флейк): `Demo/Colony chinchillas/tests/test_colony_dt_invariance.py`.

---

## 1. Проблема

До исправления траектории стресса и аффекта зависели от шага хоста `dt`:

- **Аффективная оценка:** `_derive_affective_space_inputs` возвращает драйвы **за секунду**; commit применял их **без** `× dt`, поэтому мелкий шаг перенакачивал стресс (мягкая отрицательная награда: разброс ~`0.695` при `dt ∈ {0.1, 0.25, 1.0}` на `a2bab8f`, мелкий `dt` залипал около `0.84`).
- **Двойная интеграция:** когнитивный commit плюс срезы тела могли дважды вызвать `AffectiveSpace.step` на один интервал хоста (сон/пробуждение).
- **Кортизол HPA:** `update_from_signals` каждый раз добавлял полную секундную дозу и снимал избыток фиксированным pull `0.4`, **без** учёта `dt`. Уровень и клиренс во сне не были инвариантны к дроблению шага.
- **Сон:** секунды хоста без оценки не очищали кортизол; доза HPA от бодрствования (`0.01 × wakefulness`) на sleep-commit шла как при `dt = 1`, и кортизол рос во сне.

Гены и константы нейромодуляторов **не** подгонялись.

---

## 2. Решение

### 2.1 Импульс аффекта = rate × dt

В `commit_executed_transition`, если `affective_inputs` не заданы, каждая ось из derive умножается на `time_elapsed` хоста перед `AffectiveSpace.step` (`src/agent.py`). При `dt = 1` толчок совпадает с прежним односекундным шагом.

### 2.2 Одно продвижение аффекта на тик хоста

| Механизм | Роль |
| --- | --- |
| `affect_time_credit_s` на `AffectiveSpace` | commit фиксирует уже интегрированный интервал; срезы тела тратят кредит в `AutonomousOrganismAgent.update_affect` без повторного retention |
| Sleep-commit | pending `time_elapsed` обнуляется; commit с `0`; секунды хоста всё равно клирят кортизол |
| `regulate_affect` / перегрузка | `time_elapsed=0` (только импульс регуляции) |

Колония: `_advance_autonomous_body` не крутит тело при `is_sleeping`.

### 2.3 Кортизол — `_integrate_cortisol(secretion, dt)`

`src/neuromodulators.py`. Pull `ACC_CORT_HOMEOSTATIC_DECAY = 0.4` → retain `0.6` за секунду.

- Клиренс избытка над `BASELINE_CORT`: множитель `0.6^dt` на `(current − baseline)`.
- Постоянная секреция (legacy доза за 1 с): доставлено `secretion × (1 − 0.6^dt) / 0.4` (закрытая форма при постоянной скорости и том же клиренсе).
- `dt = 1`: бит-в-бит со старой картой `cortisol += 0.4 × (baseline − current) + secretion`.
- Равновесие `baseline + secretion / pull` не зависит от `dt`; один шаг `dt` эквивален двум шагам `dt/2`.

`update_from_signals(..., dt=...)` ведёт кортизол только через `_integrate_cortisol`. На sleep-commit `Agent` интегрирует ещё не очищенные секунды хоста с `secretion = 0` до оценки при `dt = 0`.

### 2.4 Доза HPA от бодрствования

Прирост кортизола из `wakefulness.get_neuromodulator_deltas()` умножается на `_nm_appraisal_dt` (интервал оценки хоста). На sleep-commit appraisal `dt = 0`, тоническая доза выключена, клиренс работает.

---

## 3. Инварианты и тесты

| Инвариант | Тест |
| --- | --- |
| Стресс за фиксированное sim-время, `dt ∈ {0.1, 0.25, 1.0}` | `test_derived_stress_over_fixed_time_is_invariant_to_dt` (`DT_INVARIANCE_TOLERANCE = 0.08`, 10 с) |
| `_relax_deviation` к уставке с сохранением знака | `test_allostatic_map_relaxes_both_signs_toward_the_setpoint`, тесты разряда перегрузки |
| Один положительный `time_elapsed` на тик организма | `test_organism_tick_advances_affect_once_even_with_overload_and_internal_cycle`, `test_commit_plus_body_slices_integrate_the_host_interval_once` |
| Сон сытого снижает кортизол; голод поднимает | `test_fed_sleep_clears_cortisol_and_does_not_secrete`, `test_unmet_need_raises_stress_and_cortisol_and_relief_relaxes_them` |
| Расписание при `dt = 1` совпадает с `a2bab8f` | проба QA (отдельного имени нет) |
| Стационарный кортизол vs `dt` | `test_cortisol_steady_level_does_not_depend_on_dt`, `test_four_quarter_seconds_are_not_four_full_cortisol_doses` в `test_neuromodulators_phase2.py` |

Запуск:

```bash
python3 -m pytest -q tests/test_issue_78_affect_time.py tests/test_neuromodulators_phase2.py
```

Флейк демо (ссылки на объекты, не голый `id()`): `test_lifespan_factor_runner_matches_at_nominal_1x_and_10x` в `test_colony_dt_invariance.py`.

---

## 4. QA

Отчёт: [issue-78-affect-time.ru.md](../qa/issue-78-affect-time.ru.md) — **PASS** на `4bc99db`.

- `dt = 1` vs `a2bab8f` (8 коммитов): макс. \|Δкортизол\| `5.6e-17`, \|Δстресс\| `0`.
- Инвариантность мягкого стресса (10 с, награда −0.05): разброс `0.0238` (на старом коде ~`0.695`).
- Сон сытого 16 с: кортизол `0.0593 → 0.0532`, без рампы; интегратор HPA за 24 с: разброс `1.5e-6` по `dt`.
- Целевой pytest: **25 passed** за 0.43 с.

---

## 5. Известные ограничения

| Пункт | Примечание |
| --- | --- |
| Импульс CER по кортизолу | `EmotionalRegulation.apply_neuromodulator_guidance(..., gain=0.5)` на каждом commit **не** умножается на `dt`. Кортизол агента за 10 с при нулевом бодрствовании: разброс `0.0286` (допуск теста на стресс `0.08`; при `dt = 1` кривые совпадают с main). |
| Долгий штраф голода | 30 с в духе колонии: разброс стресса `0.111` — вне сценария теста (10 с, −0.05); мелкий `dt` больше не залипает высоко. |
| Плато стресса в демо | as_is plateau ≥ 0.45 — **issue #79**, вне объёма. |

---

## 6. Принцип проекта

Строгое биоподобие: когнитивное **ядро** не подгоняется под демо-хосты. Менялась только интеграция по времени существующих посекундных rate и доз; геном и константы `CORT_*` / `ACC_CORT_HOMEOSTATIC_DECAY` совпадают с `a2bab8f`.
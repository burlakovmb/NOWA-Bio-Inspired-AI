# Issue #79 — локальное заражение страхом в демо «Колония»

English: [issue-79-colony-contagion.en.md](issue-79-colony-contagion.en.md)

PR #84, ветка `team/issue-79-colony-contagion`. Колонийная часть [issue #79](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/79). Опирается на тревожный лай и аффект в симулированных секундах ([issue-54-affect-simulated-time.ru.md](issue-54-affect-simulated-time.ru.md), [issue-78-affect-time.ru.md](issue-78-affect-time.ru.md)).

Код (только демо): `Demo/Colony chinchillas/src/colony_agent.py`. Тесты: `Demo/Colony chinchillas/tests/test_issue_79_contagion.py`. **`src/` не менялся** — ядро под демо не подгонялось.

---

## 1. Проблема

До правки хост `ChinchillaAgent` размазывал эмоциональное давление по всей колонии и замыкал его в обучении:

1. **Глобальный `fearful` в конфликте:** любой сосед с `affect_tone == "fearful"` добавлял конфликт без учёта зоны и знакомства.
2. **Петля стресс→конфликт:** `conflict += stress * 0.3` от собственного стресса слушателя, затем снова рост стресса через оценку (`_derive_affective_space_inputs`).
3. **Награда от уровня миски:** в награду входил уровень общей кормушки, а не только голод/жажда животного.
4. **Двойной стресс в награде:** `reward -= stress * 0.3` штрафовал ось, уже отражённую в аффекте.
5. **Контекст `alarm_call`:** событие могло появляться при одном лишь «страшном» тоне соседа, а не в тик первого услышанного лая (см. bout в issue #54).
6. **Нет привыкания** к повторному fearful-тону знакомого в той же зоне.
7. **Нет явной скученности** у миски помимо общего социального контакта.

---

## 2. Решение (только хост)

Вся логика в `colony_agent.py`. Константы — на уровне модуля, если не указано иное.

### 2.1 Локальный fearful-тон в конфликте

`_compute_conflict(host_dt)` добавляет заражение страхом только если:

| Условие | Требование |
| --- | --- |
| Категория восприятия | `contact` (та же зона; см. `_perceive`) |
| Знакомство | `other_id` в `knowledge` (чужой в зоне — `unknown_nearby`, не `contact`) |
| Тон | `public_state.affect_tone == "fearful"` |

Вклад на соседа за тик: `FEAR_CONTAGION_CONFLICT * gain`, `gain` из `_fear_contagion_gain`. При `dt = 0` и свежей чувствительности **+0.1** к конфликту (до потолка 1.0).

**Убрано:** обход всей колонии по fearful; **убрано:** конфликт от незнакомца в той же зоне (новизна остаётся в `_compute_novelty`).

### 2.2 Привыкание и восстановление (`fear_contagion`)

На каждого знакомого соседа: `self._fear_contagion[other_id] = (sensitivity, stamp)`.

| Константа | Значение | Роль |
| --- | ---: | --- |
| `FEAR_CONTAGION_CONFLICT` | 0.1 | Множитель конфликта при полной чувствительности |
| `FEAR_CONTAGION_FLOOR` | 0.3 | Пол чувствительности после долгой экспозиции |
| `FEAR_CONTAGION_EXPOSURE_TAU_S` | 120.0 | τ при fearful в контакте |
| `FEAR_CONTAGION_RECOVERY_TAU_S` | 120.0 | τ без экспозиции (восстановление к 1.0) |

`_fear_contagion_gain(other_id, host_dt, exposed=True/False)`:

- **Экспозиция:** `sens ← FLOOR + (sens − FLOOR) × exp(−dt / τ_exposure)`.
- **Без экспозиции:** рост чувствительности к 1.0 с `τ_recovery`.

Интеграция по **симулированным секундам хоста** (`host_dt` из `sim_step`); дробление 120 с на тики эквивалентно одному длинному шагу (тесты).

### 2.3 Контекстное событие `alarm_call`

`_build_context_events` добавляет `alarm_call` только при `self._alarm_heard_this_tick`.

`_perceive_alarm_calls` сбрасывает флаг в начале, затем ставит его, если в **этом** тике впервые услышен текущий `event_id` крикуна (та же/соседняя зона, `_is_emitting_alarm()`). Повторные тики того же bout — без флага, даже пока открыто окно 2 с (`ALARM_CALL_AUDIBLE_S`).

Для этой метки заменено связывание только с видимым fearful-тоном (примечание issue #54 §7.2 для `alarm_call` устарело).

### 2.4 Нет самопетли стресс→конфликт

**Убрано:** `stress * 0.3` из `_compute_conflict`. Высокий собственный стресс сам по себе не даёт конфликта (`test_stress_alone_does_not_create_conflict`).

### 2.5 Награда только от своей физиологии

`_compute_reward`:

- **Убрано:** слагаемое от уровня общей миски при сытости.
- **Убрано:** `reward -= stress * 0.3`.
- **Сохранено:** штрафы за голод/жажду, дельты, неудачный eat/drink, социальный бонус, выравнивание при `physiology_as_policy` — в том числе **отрицательная** награда при голоде/жажде и срыве еды/питья; стресс растёт через оценку ядра (ожидаемо, без второго учёта на скаляре награды).

Сытое животное получает **0** награды при полной и пустой миске и при любом стрессе.

### 2.6 Скученность у миски

`_bowl_crowd_conflict()` добавляет `BOWL_CROWD_CONFLICT = 0.15` за **каждого лишнего** едока (`current_action == "eat"`) в зоне слушателя из `FOOD_BOWL_ZONES` (`bowl_pellets`, `bowl_hay`). Гранулы и сено — разные зоны; наблюдатель должен стоять в зоне миски.

### 2.7 Сохранение — `runtime.alarm.fear_contagion`

`_export_alarm_state` / `_restore_alarm_state` пишут и читают `fear_contagion` как `{caller_id: [sensitivity, stamp]}` рядом с `heard`, `habituation` и др.

| Случай загрузки | Поведение |
| --- | --- |
| Нет ключа | Пустой словарь; новый контакт с чувствительностью 1.0 |
| Битые / нечисловые значения | `_coerce_finite` → 1.0; затем clamp `[FEAR_CONTAGION_FLOOR, 1.0]` |
| Нет блока `runtime.alarm` | Пустой словарь; прежний путь `_anchor_alarm_stress` |

Формат habituation лая не менялся; добавлен только соседний ключ.

---

## 3. Тесты

`Demo/Colony chinchillas/tests/test_issue_79_contagion.py`:

| Тест | Что проверяет |
| --- | --- |
| `test_fearful_tone_conflicts_only_in_the_same_zone` | Зона и знакомство |
| `test_constant_fearful_neighbour_habituates_with_host_time` | Инвариантность по dt, пол, восстановление |
| `test_stress_alone_does_not_create_conflict` | Нет петли стресса |
| `test_bowl_crowding_counts_extra_eaters_in_that_zone` | Скученность |
| `test_alarm_call_label_only_when_a_call_is_heard_this_tick` | Тик `alarm_call` |
| `test_reward_ignores_bowl_level_and_stress` | Награда |
| `test_fear_contagion_save_roundtrip_and_legacy_default` | Save/load |

Соседние регрессии (QA): `test_issue_54_alarm.py`, `test_knowledge.py::test_tc08_alarm_call_affects_known_stronger_than_unknown`, `test_storage.py`.

---

## 4. QA

Отчёт: [issue-79-colony-contagion.ru.md](../qa/issue-79-colony-contagion.ru.md) — **PASS** на `068edce`. `git diff main...HEAD -- src/` пуст.

---

## 5. Наблюдаемый эффект (headless, tech lead)

Прогон колонии **1500 с**, **seed 1**, **16 агентов**. Сравнение **main** и ветки **PR #84**:

| Метрика | main | PR |
| --- | ---: | ---: |
| Средний стресс | 0.695 | 0.719 |
| Доля времени со стрессом ≥ 0.45 | 0.819 | 0.849 |
| Средний кортизол | 0.716 | 0.488 |

**Абляция (контрфакты на той же постановке):**

| Что откатили | Влияние на рост стресса | Влияние на кортизол |
| --- | --- | --- |
| Только бонус награды от полной миски (§2.5) | Объясняет **рост** среднего стресса относительно main | — |
| `stress * 0.3` в конфликте и в награде (§2.4, §2.5) | — | Объясняет **снижение** кортизола относительно main |

Средний стресс и доля ≥ 0.45 на PR остаются высокими из‑за **реального голода**: 16 животных опустошают миски примерно за 300 с, пополнение раз в `REFILL_DAY_S = 600` с (`Demo/Colony chinchillas/src/config_colony.py`, `simulation_runner.py`). Каденция кормушек и численность — настройка **среды демо**, вне scope #79.

Критерий issue «нет залипания ≥ 0.45 **только от заражения**» выполняется снятием глобального fearful и петель стресса; хроническое повышение от голода ожидаемо и вне scope (кросс-ссылка на демо-плато в [issue-78-affect-time.ru.md](issue-78-affect-time.ru.md) §5).

---

## 6. Принцип проектирования

Строгое биоподобие в `src/`: менялся только **хост** колонии (`colony_agent.py`). Импульсы лая (issue #54), корректный по `dt` аффект (issues #54, #78) и константы генома не трогались.
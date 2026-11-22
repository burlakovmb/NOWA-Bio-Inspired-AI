# Issue #80 — экономика корма в колонии (списание только при eat/drink)

English: [issue-80-colony-food-economy.en.md](issue-80-colony-food-economy.en.md)

PR #88, ветка `team/issue-80-colony-food-economy`. Колонийная часть [issue #80](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/80). Связано: [issue #74](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/74), [issue #56](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/56) (длительность действий — **вне scope**). Опирается на лай, аффект и заражение ([issue-54-affect-simulated-time.ru.md](issue-54-affect-simulated-time.ru.md), [issue-78-affect-time.ru.md](issue-78-affect-time.ru.md), [issue-79-colony-contagion.ru.md](issue-79-colony-contagion.ru.md)).

Код (только демо): `Demo/Colony chinchillas/src/colony_agent.py`. Тесты: `Demo/Colony chinchillas/tests/test_issue_80_food_economy.py`, `Demo/Colony chinchillas/tests/test_resources.py`. **`src/` не менялся** — ядро под демо не подгонялось.

---

## 1. Проблема

Каждую симулированную секунду `_apply_metabolism_second` (из `_resource_metabolism_step`, когда у агента накопилась 1 с метаболизма) для **каждого бодрствующего** агента **безусловно** уменьшала общие миски:

- **Корм:** `consume_food(0.0003 * RESOURCE_CONSUMPTION_MULTIPLIER, …)` раз в секунду на бодрствующего.
- **Вода:** `water -= 0.0001 * RESOURCE_CONSUMPTION_MULTIPLIER` раз в секунду на бодрствующего.

Списание **не** зависело от действий `eat` / `drink`, успешного acquire и порогов голода/жажды. Реальные укусы по-прежнему в `_try_acquire_resource`: `0.003 * RESOURCE_CONSUMPTION_MULTIPLIER` за вызов.

**Наблюдаемый сбой (issue #80, stress repro):** ~93% расхода корма — пассивный сток без поедания; при **16 агентах** общая миска пуста ~54–65% времени, а пополнение (`REFILL_DAY_S = 600` с в `config_colony.py` / `simulation_runner.py`) не успевает. Голодный стресс накапливается, даже если животное не ест у миски. Это маскирует поведенческую динамику (скученность, политика, заражение) и делает хронический голод главным драйвером стресса (см. плато в [issue-79-colony-contagion.ru.md](issue-79-colony-contagion.ru.md) §5).

---

## 2. Решение (только хост)

Вся логика в `colony_agent.py`. Типы ресурсов и пополнение (`shared_resources.py`, `simulation_runner.py`, `config_colony.py`) в PR **не** менялись.

### 2.1 Убрать пассивное списание из метаболизма

В `_apply_metabolism_second` после роста голода/жажды, критических импульсов и раннего выхода при сне:

| Убрано | Сохранено |
| --- | --- |
| Секундный `consume_food(0.0003 * …)` | Рост hunger/thirst (`HUNGER_ACCUMULATION_PER_S`, `THIRST_ACCUMULATION_PER_S`) |
| Секундный `water -= 0.0001 * …` | Критические импульсы при сильном голоде/жажде |
| — | Ранний выход при `is_sleeping` или `current_action == "sleep"` |
| — | **Штрафы пустой миски:** при `pellets + hay <= 0` — аффект + `RESOURCE_MISSING_ENERGY_PENALTY_PER_S`; при `water <= 0` — аффект + `WATER_MISSING_ENERGY_PENALTY_PER_S` (с `RESOURCE_CONSUMPTION_MULTIPLIER`) |

Бодрствующие агенты больше не «пьют» общий запас просто от метаболизма.

### 2.2 Списание только при успешном eat/drink

Миски падают **только** в `_try_acquire_resource`, размер порции и «раз за вызов» без изменений:

| Ресурс | Условие (кратко) | Списание |
| --- | --- | --- |
| `food_pellets` | Не сон; опциональный physiology gate; availability > 0.05 | `consume_food(0.003 * RESOURCE_CONSUMPTION_MULTIPLIER, …)` + `EAT_RELIEF` |
| `water` | Не сон; опциональный physiology gate; water > 0.02 | `water -= 0.003 * RESOURCE_CONSUMPTION_MULTIPLIER` + `DRINK_RELIEF` |

`sim_step` по-прежнему один раз вызывает `_interpret_action`; ветки `eat` и `drink` взаимоисключающие — не больше **одного** acquire за тик на агента.

**Явно вне scope этого issue:**

- Порча / пассивный распад не добавлялись.
- `REFILL_DAY_S` не менялся (`600.0`).
- Длительность действий (#56) не трогали.
- **`src/`** (геном, оценка, гиппокамп) без изменений — строгое биоподобие.

### 2.3 Биологический смысл

Общий корм и вода — **физическая миска**. Шиншилла уменьшает запас только когда **ест** или **пьёт** у миски (действие хоста + acquire), а не от того, что просто бодрствует в другой зоне. Голод и жажда по-прежнему растут со временем; пустые миски по-прежнему бьют по аффекту и энергии — дефицит без невидимого испарения.

### 2.4 Неизменённая семантика колонии

`_bowl_crowd_conflict`, `current_action == "eat"` для скученности и порядок `sim_step` (конфликт до `_interpret_action`) в PR **не** менялись; тесты скученности issue #79 остаются валидными.

---

## 3. Тесты

### 3.1 `test_issue_80_food_economy.py`

| Тест | Что проверяет |
| --- | --- |
| `test_awake_animals_below_the_need_do_not_drain_the_bowls` | 24 с, три агента ниже порогов eat/drink; миски неизменны; голод/жажда растут |
| `test_empty_colony_does_not_drain_the_bowls` | 30 с, 0 агентов; миски неизменны |
| `test_eat_and_drink_events_match_the_bowl_on_a_metabolism_tick` | Один укус (`BITE = 0.003 * RESOURCE_CONSUMPTION_MULTIPLIER`) за тик eat/drink; 9 кормящих тиков + idle explore; падение миски = сумма приёма |
| `test_hunger_and_thirst_still_accumulate_while_awake` | 20 с бодрствования, полные миски, рост потребностей без списания |
| `test_empty_bowls_still_cost_energy_and_are_not_sipped` | Пустые миски: штрафы энергии, уровни 0, без пассивного стока |
| `test_sleep_still_skips_the_empty_bowl_penalty_and_the_bowls` | Сон: миски и энергия без штрафа пустой миски, голод/жажда растут |

### 3.2 `test_resources.py`

| Тест | Что проверяет |
| --- | --- |
| `test_tc01_two_agents_basic_survival_loop` | **Обновлён:** 300 с, два агента; `abs(food_drop - sum(eaten)) <= 1e-9` и то же для воды; drop > 0 тогда и только тогда, когда список приёма непуст |
| `test_tc01_two_agents_survive_300s` | Регрессия выживания |
| `test_tc04_wheel_is_exclusive_resource` | Эксклюзивность колеса (регрессия) |

### 3.3 Соседние регрессии (QA)

`Demo/Colony chinchillas/tests/test_issue_79_contagion.py` (включая `test_bowl_crowding_counts_extra_eaters_in_that_zone`). В фиксированном прогоне QA не запускались `test_tc26d_sleeping_agent_does_not_consume_shared_food_or_water` и `test_tc26e_sleeping_agent_cannot_directly_eat_or_drink`; логически они согласованы с ранним выходом при сне и guard в acquire.

---

## 4. QA

Отчёт: [issue-80-colony-food-economy.ru.md](../qa/issue-80-colony-food-economy.ru.md) — **PASS** на `83e1741`. `git diff origin/main -- src/` пуст.

---

## 5. Наблюдаемый эффект (headless, tech lead)

Прогон колонии **1500 с**, **16 агентов**, сиды **1** и **2**. Сравнение **`origin/main`** `89c10a0` и **PR** `83e1741`:

| Метрика | main `89c10a0` | PR `83e1741` |
| --- | ---: | ---: |
| Доля времени с пустой миской корма | 54% | 0% |
| Доля времени с пустой миской воды | 50% | 0% |
| Средний голод | 0.60 | 0.28 |
| Доля голодных (H > 0.4) | 0.64 | 0.25 |
| Средний кортизол | 0.47 | 0.26 |
| Средняя энергия | 0.71 | 0.97 |
| Средний стресс (seed 1 / seed 2) | 0.68 / 0.66 | 0.63 / 0.58 |
| Доля fearful (seed 1 / seed 2) | 0.74 / 0.72 | 0.65 / 0.64 |

---

## 6. Вывод и ограничения

После снятия пассивного стока **голод больше не главный источник стресса** в сценарии на 16 агентов: время пустых мисок и средний голод резко падают; энергия и кортизол улучшаются. **Остаточный стресс и доля fearful** (~0.58–0.63 стресс, ~64–65% fearful на PR) идут из других источников хоста и ядра (лай, заражение, социальный конфликт, фрустрация политики и т.д.) и **вне scope #80**.

Подгонка численности под `REFILL_DAY_S`, явная порча или привязка списания к длительности действий (#56) — отдельные задачи по среде демо или follow-up, не часть этого фикса.

---

## 7. Принцип проектирования

Строгое биоподобие в `src/`: менялся только **хост** колонии (`colony_agent.py`). Метаболизм по-прежнему интегрируется по симулированным секундам на агента; изменён только **учёт** общих мисок — списание перенесено на реальный eat/drink в acquire.
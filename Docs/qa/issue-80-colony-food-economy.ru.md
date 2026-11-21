# QA issue #80 — корм и вода только на eat/drink

Ветка: `team/issue-80-colony-food-economy`. HEAD продукта на момент прогона: `83e1741` (`83e1741c8d30654cf930d726ea022a98e4819b7b`). PR: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/88. Issue: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/80. База diff: `origin/main` (`89c10a0`, `89c10a0d680b6546f1c30522743292e1081b3f0b`).

Код продукта и тесты в этом проходе не менялись. Новый PR не создавался, комментариев на GitHub нет, мержа нет. CI не ждали. Длинные тесты и симуляция 16 агентов не запускались.

Машина: Python 3.12.3, pytest 9.2.0.

## Вердикт

**PASS** (`83e1741`).

Семь пунктов чеклиста проходят. Пассивное секундное списание из `_apply_metabolism_second` снято. Порция eat/drink остаётся `0.003 * RESOURCE_CONSUMPTION_MULTIPLIER` и списывается один раз за тик действия. Голод и жажда растут, ранний выход во сне и штрафы пустой миски на месте. `src/` не изменён. `REFILL_DAY_S` не менялся (`600.0`), порчи нет.

## Покрытие (сценарии: 7 пройдено / 0 провалено / 0 не запускалось)

| # | Проверка | Результат |
| --- | --- | --- |
| 1 | `git diff origin/main -- src/` пуст | Pass. 0 байт. В `--name-only` три файла демо: `colony_agent.py` (`+7/−9`), `tests/test_issue_80_food_economy.py` (`+238`), `tests/test_resources.py` (`+37/−2`) |
| 2 | `_apply_metabolism_second` против `main` | Pass. Вызова `consume_food` нет, присваивания `water` нет. Убраны пассивные `consume_food(0.0003 * RESOURCE_CONSUMPTION_MULTIPLIER)` и `water - (0.0001 * RESOURCE_CONSUMPTION_MULTIPLIER)`. Рост hunger/thirst и критические импульсы стоят до раннего выхода `is_sleeping or current_action == "sleep"`. Штраф пустого корма (`pellets + hay <= 0`: stress `0.02`, valence `-0.02`, intensity `0.5`, `RESOURCE_MISSING_ENERGY_PENALTY_PER_S`) и пустой воды (`water <= 0`: stress `0.02`, intensity `0.4`, `WATER_MISSING_ENERGY_PENALTY_PER_S`) сохранены |
| 3 | Одно списание на тике eat/drink, других путей нет | Pass. `sim_step` вызывает `_interpret_action` один раз. Ветки `eat` / `drink` взаимоисключающие: один вызов `_try_acquire_resource`. Еда: один `consume_food(0.003 * RESOURCE_CONSUMPTION_MULTIPLIER)`. Вода: одно присваивание `water - (0.003 * RESOURCE_CONSUMPTION_MULTIPLIER)`. Функция в diff не входила. `rg` по `Demo/Colony chinchillas/src`: `consume_food` только определение в `shared_resources.py` и вызов в `_try_acquire_resource`; совпадений `.water -=`, `food_pellets -=`, `hay -=` нет. `config_colony.py`, `simulation_runner.py`, `shared_resources.py` в diff против `main` не входят |
| 4 | `tc01` не ослаблен | Pass. `test_tc01_two_agents_basic_survival_loop` сверяет падение миски с суммой съеденного и выпитого: `abs(food_drop - sum(eaten)) <= 1e-9` и то же для воды. Отдельно: падение `> 1e-12` тогда и только тогда, когда список приёма непуст. Это не проверка «миска не упала» |
| 5 | Заданный pytest | Pass. 16 passed, 13.55 с, exit 0. Состав ниже |
| 6 | Пустая колония и сон не трогают миски | Pass. `test_empty_colony_does_not_drain_the_bowls`: 0 агентов, `run_for(30, dt=1)`, миски равны старту. `test_sleep_still_skips_the_empty_bowl_penalty_and_the_bowls`: сон, пустые миски, одна секунда метаболизма, уровни `0`, энергия без штрафа, голод и жажда растут. Ранний выход стоит до любой записи в миски; `_try_acquire_resource` на food/water при сне возвращает False до списания |
| 7 | `_bowl_crowd_conflict` и `current_action == "eat"` | Pass. Метод и вызов из `_compute_conflict` в diff не входят. Едок по-прежнему агент в зоне миски с `current_action == "eat"`. `_interpret_action` по-прежнему ставит `current_action = action` до единственного acquire, поэтому eat по-прежнему публикует `"eat"`. Порядок `sim_step` тот же: конфликт считается до `_interpret_action`. `test_bowl_crowding_counts_extra_eaters_in_that_zone` в неизменённом `test_issue_79_contagion.py` проходит |

Заданный прогон, exit 0:

```
SDL_VIDEODRIVER=dummy pytest \
  "Demo/Colony chinchillas/tests/test_issue_80_food_economy.py" \
  "Demo/Colony chinchillas/tests/test_resources.py" \
  "Demo/Colony chinchillas/tests/test_issue_79_contagion.py" -q
```

`16 passed in 13.55s`

Шесть тестов `test_issue_80_food_economy.py`: бодрствующие ниже порога потребности не трогают миски, голод и жажда за 24 с растут на `24 * HUNGER_ACCUMULATION_PER_S` / `THIRST_ACCUMULATION_PER_S`; пустая колония; один укус eat и один глоток drink за тик `dt=1` равны `BITE`, падение миски равно сумме приёма, девять таких тиков и следующий explore миски не двигают; накопление голода и жажды 20 с при полных мисках; пустые миски дают оба штрафа энергии и сами не убывают; сон пропускает штраф и не меняет пустые миски.

Три теста `test_resources.py`: `tc01` на равенство падения и приёма (300 с, два агента), `test_tc01_two_agents_survive_300s`, `test_tc04_wheel_is_exclusive_resource`.

Семь тестов `test_issue_79_contagion.py`, включая `test_bowl_crowding_counts_extra_eaters_in_that_zone`.

Вне этого прогона, файл не в diff: `test_tc26d_sleeping_agent_does_not_consume_shared_food_or_water` (полные миски, метаболизм во сне) и `test_tc26e_sleeping_agent_cannot_directly_eat_or_drink` (acquire во сне возвращает False, полные миски на месте). Не запускались: команда прогона была фиксированной.

## Контекст замера тимлида

Не воспроизводился. 16 агентов, 1500 с, сиды 1 и 2, `main` `89c10a0` против PR `83e1741`. Где дана одна цифра, в задании она одна. Пара через слэш — сиды 1 и 2 в этом порядке.

| Метрика | main `89c10a0` | PR `83e1741` |
| --- | --- | --- |
| Доля времени с пустой миской корма | 54% | 0% |
| Доля времени с пустой миской воды | 50% | 0% |
| Средний голод | 0.60 | 0.28 |
| Доля голодных (H>0.4) | 0.64 | 0.25 |
| Кортизол | 0.47 | 0.26 |
| Энергия | 0.71 | 0.97 |
| Средний стресс (сиды 1 / 2) | 0.68 / 0.66 | 0.63 / 0.58 |
| Доля fearful (сиды 1 / 2) | 0.74 / 0.72 | 0.65 / 0.64 |

Вывод тимлида, принят как контекст: голод больше не главный источник стресса. Остаток стресса из других источников, вне scope #80.

## Дефекты

Нет.

## Рекомендации

Полный pytest и длинные тесты (`test_fix_colony_no_rest`, `test_colony_dt_invariance`) остаются на уже зелёном CI коммита `83e1741`. Повторный замер 16 агентов не нужен для этого чеклиста.

## Готовность

Да, по этому чеклисту.

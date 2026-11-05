# QA issue #22 — старость колонии в сим-секундах

Ветка: `team/issue-22-colony-lifespan-sim-seconds`. Раунд 2 проверил HEAD `9d49e96`.
PR: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/61
Issue: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/22
База: `main` @ `a8d7503` (merge-base).
English: [issue-22-qa.en.md](issue-22-qa.en.md).
Спека: [issue-22-colony-lifespan-sim-seconds.ru.md](../specs/issue-22-colony-lifespan-sim-seconds.ru.md).

PASS раунда 1 — продуктовый коммит `73c2e87` (заметки QA `3c3cb54`, `b26956e`). Эта заметка покрывает тот объём плюс `eecc611` (множитель гена), `f372606` (предел в медиа), `9d49e96` (спека и документы колонии) и соседний фикс тестов labile `8b722f7`. Этот проход QA код продукта не менял. Новый PR не открывался.

Машина: Python 3.12.3, pygame 2.6.1, pytest 9.2.0.

## Вердикт

**PASS** (`9d49e96`).

`lt_max_lifespan_factor` применяется. `max_lifespan_age_s = COLONY_MAX_LIFESPAN_AGE_S * genome.genes.get("lt_max_lifespan_factor", 1.0)`. Измеренные пределы — 6750, 13500 и 27000 с. Без генома остаётся 13500 с. Новорождённый после кроссовера получает свой предел. `colony_scripted_old_age_s` читает `MortalitySystem.max_lifespan_age_s` этой особи. Основатель с множителем 2.0 принудительно умирает на 27000 с с причиной `old_age`. Особь в стиле промо без генома — на 13500 с с той же причиной. `git diff origin/main -- src` пуст. Пара спеки совпадает с кодом и сама с собой. Набор колонии зелёный.

Известные оговорки, это не FAIL: база ×15 против ×22.5, доля lifespan в health-index и потеря `genome` при save/load колонии. Один раздел модульной спеки колонии всё ещё описывает старый бюджет шагов (minor).

## Покрытие

Сценарии: **17 пройдено / 0 провалено / 3 не запускалось**.

| # | Сценарий | Результат |
| --- | --- | --- |
| 1 | Без генома и множитель 1.0 → 13500 с; множители 0.5 и 2.0 → 6750 с и 27000 с; поле шагов 20000 | Pass |
| 2 | `old_age` в одном sim-age при dt 1 с и 10 с; при множителе 2.0 особь ещё жива на 13500 с | Pass (`test_lifespan_factor_scales_old_age_and_matches_across_dt`) |
| 3 | Бегун на номинальных 1× и 10× умирает на пределе этой особи; число решений разное | Pass (`test_lifespan_factor_runner_matches_at_nominal_1x_and_10x`) |
| 4 | Предел новорождённого — по гену после кроссовера; родители остаются на 27000 с и 6750 с; три объекта `MortalitySystem` | Pass. Проба, seeds 13/14: множитель детёныша 1.25 → 16875 с |
| 5 | Рождение, когда геном есть только у одного родителя | Pass. Геном детёныша `None`, предел 13500 с; родитель с геномом сохраняет 27000 с или 6750 с |
| 6 | `colony_scripted_old_age_s` | Pass. 27000 / 6750 / 13500 для множителя 2.0, множителя 0.5 и особи без генома |
| 7 | `render_evolution_media._kill_oldest` на этих трёх | Pass. Причина `old_age`, `agent.age` остаётся 250, `lived_steps` остаётся 17, список бегуна пуст |
| 8 | Обновление в стиле промо, `MortalitySystem.update` без генома | Pass. Причина `old_age`, предел 13500 с, `age` остаётся 250, `lived_steps` остаётся 9 |
| 9 | Границы реестра | Pass. 0.5 и 2.0 собираются; 0.499, 2.001, 0.0 и 3.0 дают `ValueError` |
| 10 | Молодая особь, множитель 2.0, `lived_steps` 50000, затем `_age_step(0.1)` | Pass. Жива, возраст 10.1, причина пустая |
| 11 | Истощение в возрасте 400, энергия 0.08, множитель 0.5, `_age_step(0.5)` | Pass. `exhaustion` в 400.5, не `old_age` |
| 12 | Возраст уже выше предела; `max_lifespan_age_s is None` | Pass. Возраст 30000 с при множителе 2.0 всё ещё `old_age`, возраст не меняется. Сброшенный cap берёт формулу гена (6750 с) |
| 13 | Случайный основатель, `GenomeVector.random` от `random.Random(11)` | Pass. Множитель 0.8563250131981743, предел 11560.387678175353, helper возвращает этот предел |
| 14 | `git diff origin/main -- src` | Пусто. `colony_storage.py` и `swarm_analytics.py` в diff ветки нет |
| 15 | Пара спеки, `COLONY_SPEC`, `IMPLEMENTATION_DESCRIPTION` | Pass. Файлы спеки по 94 строки. Числовые токены совпадают (100 = 100), включая 6750, 13500, 27000, 20250 |
| 16 | `python3 -m pytest -q "Demo/Colony chinchillas/tests"` | **232 passed, 1 warning**, выход 0, 327.60 с. Предупреждение — `pkg_resources` у pygame. `test_founders_do_not_die_of_exhaustion_at_10x` прошёл внутри этого прогона (отдельно не перезапускался) |
| 17 | Пять тестов labile, которые раньше давали `TypeError` из вложенного `pytest.approx` | **5 passed**, 0.21 с, после `8b722f7`. Повторно не падают |

Не запускалось:

| # | Сценарий | Почему |
| --- | --- | --- |
| 1 | Полный GIF-рендер `render_evolution_media` / `render_promo_media` | Писал бы `docs/media`. Вызовы смерти выполнены напрямую |
| 2 | Полный корневой `python3 -m pytest -q` | Вне минимума этого раунда. Запущены набор колонии и пять тестов labile |
| 3 | Ручной прогон раунда 1 с возраста 0 при `dt = 1/12` (162000 обновлений) | Не повторялся. Автотесты предела по умолчанию в наборе снова прошли (`test_old_age_lifespan_matches_across_dt`, `test_runner_old_age_matches_at_nominal_1x_and_10x`, `test_tc14_colony_old_age_uses_sim_seconds`, `test_tc28_old_age_follows_biological_age_not_decision_steps`). Файл dt-инвариантности плюс эти два именных теста: **24 passed**, 98.75 с |

`git status` после наборов: чисто. Игнорируются только `.pytest_cache/`, `Demo/Colony chinchillas/logs/` и `__pycache__`. Каталога `docs/` в нижнем регистре нет.

## Дефекты

### [MINOR] Модульная спека всё ещё говорит, что старость идёт по бюджету шагов

- **Шаги**: 1) Открыть раздел 10 в `Demo/Colony chinchillas/Docs/SPEC_ChinchillaAgent_NOWA.en.md` и `.ru.md`. 2) Сравнить с `ChinchillaAgent` и с `Docs/specs/issue-22-colony-lifespan-sim-seconds.ru.md`.
- **Ожидалось**: Старость — биологический возраст в сим-секундах, с масштабом `lt_max_lifespan_factor`.
- **Факт**: Раздел 10 по-прежнему говорит, что колония не задаёт жёсткий срок жизни в секундах и что `old_age` идёт по бюджету шагов.
- **Где**: `Demo/Colony chinchillas/Docs/SPEC_ChinchillaAgent_NOWA.en.md`, `.ru.md`, раздел 10.
- **Severity**: minor

Дефектов уровня blocker, critical и major нет.

## Известные оговорки (не FAIL)

Сверены с кодом и с открытыми пунктами спеки. Вердикт из-за них не меняется.

| Тема | Что проверено |
| --- | --- |
| ×15 против ×22.5 | Базовая константа по-прежнему `15 * MATURITY_AGE_S = 13500`. Альтернатива `22.5 * MATURITY_AGE_S = 20250` есть только в разделе 6 спеки. Ген умножает базу ×15 и этот выбор не заменяет |
| Доля lifespan в health-index | `compute_health_index` по-прежнему ставит `lifespan` как среднее `lived_steps`, делённое на `_max_lifespan_steps` (`colony_gui/swarm_analytics.py`). Возрастной предел в этот знаменатель не входит. `swarm_analytics.py` в diff ветки нет |
| Save/load генома | `ColonyStorage._serialize_agent` не пишет `genome`. `_deserialize_agent` собирает `ChinchillaAgent` без него. Проба: множитель 2.0, возраст 14000 с, энергия 0.9, `lived_steps` 40. После загрузки `genome is None`, предел 13500 с, возраст по-прежнему 14000 с. Следующий `_age_step(0.1)` пишет `old_age` в возрасте 14000.1. Раздел 6 спеки называет это прежним ограничением |

## Рекомендации

- Поправить раздел 10 `SPEC_ChinchillaAgent_NOWA` в обоих языках, чтобы он совпал с возрастным пределом. Это единственный оставшийся в дереве документ, который всё ещё описывает старое правило.
- Позже можно сохранять `genome` (или уже посчитанный cap) в `ColonyStorage` и перевести член lifespan в health-index на `max_lifespan_age_s`. Оба пункта уже записаны как последующие. Когда это появится, нужен тест save/load: множитель 2.0 должен пережить загрузку.
- Тесты гена, новорождённого и скриптовой смерти, которые перечисляет спека, есть и зелёные. Для этого PASS ещё тесты не нужны.
- Тело PR #61 всё ещё говорит, что файлы спеки оставлены техническому писателю. `9d49e96` их уже обновил. Имеет смысл поправить одну фразу в тексте PR. Флажки CLA не трогались.

## Готовность к релизу

**С оговорками.** DoD раунда 2 выполнен: формула гена, media helper и спека issue вместе с обновлёнными документами цикла колонии согласованы; тесты гена и media зелёные; эта пара EN+RU фиксирует факт. Не мержить только по этой заметке, если minor-раздел спеки обязан быть чистым до merge. Три оговорки выше — принятые остатки, не блокеры релиза #22.

## Вопросы / блокеры

Блокеров нет.

Не блокирует: править ли раздел 10 `SPEC_ChinchillaAgent_NOWA` до merge или отдельным follow-up? Приёмочная спека и `COLONY_SPEC` / `IMPLEMENTATION_DESCRIPTION` ген уже описывают.

## Факты раунда 2

Формула в `Demo/Colony chinchillas/src/colony_agent.py`:

```text
max_lifespan_age_s = COLONY_MAX_LIFESPAN_AGE_S * genome.genes.get("lt_max_lifespan_factor", 1.0)
```

`_colony_max_lifespan_age_s` берёт 1.0, если `genome` нет или ключа нет. `ChinchillaAgent.__init__` передаёт это значение в `MortalitySystem` и по-прежнему передаёт `max_lifespan_steps=COLONY_MAX_LIFESPAN_STEPS` (20000). После кроссовера `_inherit_nowa_from` назначает геном детёныша и снова ставит `mortality_system.max_lifespan_age_s`. `GenomeVector` отвергает значения вне 0.5..2.0, поэтому настоящий геном не выходит из 6750..27000 с. `AgentFactory.spawn` по-прежнему не путь рождения колонии. `git diff origin/main -- src` ничего не печатает, значит `src/mortality.py` не менялся: при заданном пределе возраста `old_age` — это `biological_age_s >= max_lifespan_age_s`, и поле шагов не является этим порогом.

`colony_scripted_old_age_s` читает `mortality_system.max_lifespan_age_s` и возвращает `max(agent.age, cap)`. Если cap равен `None`, helper возвращается к той же формуле гена. `_kill_oldest` в `tools/render_evolution_media.py` и `simulate_promo_lineage` в `tools/render_promo_media.py` оба передают это значение как `biological_age_s`. Обратно в `agent.age` они его не пишут и не ставят `lived_steps` в 20000. Энергия 0.5 и бодрствование 0.2 не дают истощению и депривации сна сработать раньше. Основатели промо создаются без генома.

Регрессия предела по умолчанию в том же наборе: `test_tc14_colony_old_age_uses_sim_seconds` и `test_tc28_old_age_follows_biological_age_not_decision_steps` прошли. Отдельный основатель с множителем 2.0, возраст 250, `lived_steps` 17, обновлённый через helper, покинул бегуна с причиной в журнале `old_age`.

Документы на `9d49e96`: `Docs/specs/issue-22-colony-lifespan-sim-seconds.en.md` и `.ru.md` задают формулу, диапазон 6750..27000, media helper, восемь проверок хоста и три открытых пункта. `Demo/Colony chinchillas/Docs/COLONY_SPEC.en.md` / `.ru.md` и `IMPLEMENTATION_DESCRIPTION.en.md` / `.ru.md` задают тот же индивидуальный продукт. Опечатка пробела из раунда 1 в английском открытом пункте ("product/ biology") исчезла; строка теперь `22.5 * MATURITY_AGE_S = 20250`. `Docs/arxiv_NOWA_en.md` и `Docs/arxiv_NOWA_ru.md` в этот diff не входили.

## Раунд 1, вручную не повторялся

Прежний текст этого файла говорил, что ген предел не масштабирует. Эта фраза снята. Раунд 1 измерил немасштабированный предел: `old_age` на 13500 с при `dt` `1/12`, `0.25`, `1`, `2.5` и `10`, и кадры бегуна `1/12` (12 решений), `0.25`, `2.5` (4 решения), `0.07` и `10`. Эти ручные прогоны не повторялись. Автотесты, которые фиксируют предел по умолчанию, снова прошли внутри 232. Истощение, депривация сна и раздельные объекты NOWA у матери, отца и детёныша по-прежнему закрыты набором. Прежний снимок CI (run 42061921160, пять падений `pytest.approx`) заново не запрашивался. Локально эти пять тестов на pytest 9.2.0 теперь проходят.

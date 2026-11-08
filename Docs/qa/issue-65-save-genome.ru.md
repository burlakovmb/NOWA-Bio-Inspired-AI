# QA issue #65 — сохранение колонии удерживает темперамент из генома и родословную

Ветка: `team/issue-65-save-genome`. Проверен код `fac946f`. Спека сверху: `6ee14ba`.
PR: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/66
Issue: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/65
База: `origin/main` @ `6055c6a` (merge #64). `ColonyStorage` на этом коммите — формат сохранения до фикса.
English: [issue-65-save-genome.en.md](issue-65-save-genome.en.md).
Спека: [issue-65-save-genome.ru.md](../specs/issue-65-save-genome.ru.md).

Код продукта в этом проходе QA не менялся. Новый PR не создавался. Полный `pytest` локально не запускался.

Машина: Python 3.12.3, pygame 2.6.1, pytest 9.2.0. Проба и целевой pytest шли с `NOWA_STRICT_LEARNING=1`. `SDL_VIDEODRIVER=dummy`.

## Вердикт

**PASS** (`fac946f`).

Загрузка назначает сохранённый геном уже после конструктора `ChinchillaAgent`, затем `_apply_saved_genome` вызывает `AgentFactory._apply_genome_to_agent` и записывает обратно прожитые энергию, `social_drive` и пять уровней нейромодуляторов. У реального потомка `axis_decay["stress"]` вернулся геном `0.860535`, а не конструкторский `0.75`. `genome_inheritance_meta` проходит round-trip, включая старый `crossover_alpha`. Потомок остаётся `mode == "recombined"`. Мать остаётся `mode == "founder"`. Файл, записанный `ColonyStorage` с `origin/main` (без новых ключей), загружается, геном применяется заново, энергия и `social_drive` сохраняются, meta остаётся `{}`, метка основателя не ставится. `SCHEMA_VERSION` остаётся `1`. `git diff origin/main...fac946f -- src` пуст.

CI pytest на коммите кода `fac946f` прошёл (run [42484846043](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/actions/runs/42484846043), 14m36s). `gh pr checks 66` на момент проверки был ещё `pending` на коммите спеки `6ee14ba` (run [42486161645](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/actions/runs/42486161645)). Этот прогон не ждали.

## Покрытие

| # | Проверка | Результат |
| --- | --- | --- |
| 1 | Логика diff: геном заново, затем энергия, `social_drive`, уровни нейромодуляторов; meta на месте; потомок не становится основателем | Pass. Ниже |
| 2 | `tests/test_storage.py` и `tests/test_issue27_inheritance.py` | **11 passed**, 0.33 s, exit 0 |
| 3 | Одно реальное рождение (`_start_pregnancy` → `_give_birth`), save → load | Pass. Фенотип, прожитые энергия / social / NM / affect curiosity и meta совпали. Мать осталась founder |
| 4 | Та же колония, сохранённая `ColonyStorage` с `origin/main` (`6055c6a`) и загруженная фиксом | Pass. Новых ключей в файле нет. Ось стресса `0.860535`. Meta `{}`. Загрузчик до фикса на том же файле по-прежнему оставляет стресс `0.75` |
| 5 | Драйвы curiosity / exploration после 60 симулированных секунд | Известное ограничение, не FAIL. Ниже |

Не запускалось:

| # | Сценарий | Почему |
| --- | --- | --- |
| 1 | Полный `python3 -m pytest -q` | CI pytest на `fac946f` |
| 2 | Много поколений или много сидов | Вне этого прохода. Один помёт, один сид |
| 3 | Интерактивный GUI колонии | Список отрисовки инспектора прочитан. Дисплей не требовался |

## Что делает diff

`_restore_saved_agent` восстанавливает runtime (энергия, `social_drive` и `neuromodulator_levels`, если ключ есть) и affect, затем назначает `agent.genome` и срок жизни, затем вызывает `_apply_saved_genome`. Тот читает `genome.to_agent_params()`, снимает энергию, `social_drive` и пять концентраций, вызывает `_apply_genome_to_agent` внутри `initializing()` и записывает снимок обратно.

`_apply_autonomous_params` зовёт `init_autonomous_runtime` без `force_recreate`. Десериализатор уже собрал новый runtime, поэтому вызов оставляет этот объект, а `set_drive` пишет генетические baselines для `curiosity`, `social_drive` и `exploration`. Следующее `agent.social_drive = social_drive` возвращает прожитое social. Энергия идёт тем же порядком. Концентрации нейромодуляторов выставляются ещё раз после apply.

`genome_inheritance_meta` пишется у каждого агента. При загрузке meta заменяется только если ключ есть. `ChinchillaAgent.__init__` ставит `mode: "founder"` только когда геном передан в конструктор. Загрузка его не передаёт, поэтому отсутствующий ключ остаётся `{}` и не становится founder. Meta потомка, если она есть, затирает этот пустой словарь уже после apply.

`_serialize_inheritance_meta` сохраняет любой лишний JSON-ключ. Проверочное `crossover_alpha: 0.5` уцелело.

## Проба

Родители на противоположных границах `GENE_REGISTRY`. Мать `rng_seed=65`, отец `rng_seed=66`. Рождение: `_start_pregnancy(father.agent_id)`, затем `_give_birth` (колониальный путь, который зовёт `_create_offspring`). Помёт 1: `G1A1SF`, поколение 1, родители `mom-65` / `dad-65`, lineage `adaxlin`, `crossover_mode == "uniform"`.

`af_decay_stress` этого генома — `0.860535` (мутация от родительских концов `0.55` и `0.88`). После нового save/load `axis_decay["stress"]` равен `0.860535`. Тот же файл, загруженный классом до фикса, даёт `0.75` (`DEFAULT_AFFECTIVE_DECAY` в `src/affective_space.py`).

Прожитое, выставленное на детёныше и сохранённое: энергия `0.37`, `social_drive` `0.15`, affect curiosity `0.31` (boredom `0.69`), dopamine `0.61`, norepinephrine `0.58`, serotonin `0.27`, cortisol `0.44`, acetylcholine `0.36`. Новая загрузка совпала по всем. Предупреждений при загрузке не было. Генетический baseline social у этого детёныша — `0.05`, поэтому `0.15` — прожитое значение, а не baseline из `set_drive`. Meta совпала, включая `crossover_alpha == 0.5`. Режим потомка остался `recombined`. Режим матери остался `founder`. Lineage остался `adaxlin`, не имя детёныша.

Файл эпохи main содержит `genome` и не содержит `genome_inheritance_meta` и `runtime.neuromodulator_levels`. Новый загрузчик: фенотип совпал (стресс `0.860535`), энергия `0.37`, `social_drive` `0.15`, meta `{}`, lineage `adaxlin`. Уровни нейромодуляторов откатились к свежему агенту: dopamine `0.1`, norepinephrine `0.1`, serotonin `0.1`, cortisol `0.05`, acetylcholine `0.1`. Это файл до #65: концентраций он не хранил. Новое сохранение их хранит (`schema_version` `1`).

## Curiosity и exploration

Не сохраняются. После 60 симулированных секунд `_advance_autonomous_body` (wall `0.088` s, шаг `COLONY_BODY_STEP_S` = `1/12`) драйвы детёныша ушли с генетических baselines:

| Драйв | При рождении | После 60 s | После load |
| --- | --- | --- | --- |
| `curiosity` | 0.0500 | 1.0000 | 0.0500 |
| `exploration` | 0.3500 | 0.8493 | 0.3500 |
| `goal_tension` | 0.0800 | 0.6777 | 0.0800 |
| `energy_need` | 0.0200 | 0.0308 | 0.0200 |
| `social_drive` | 0.0500 | 0.5000, затем выставлен 0.15 | 0.1500 |

`curiosity` и `exploration` возвращаются к baselines генома (`dr_curiosity_baseline` `0.05`, `dr_exploration_baseline` `0.35` у этой крайней пары). `goal_tension` и `energy_need` возвращаются к начальным значениям нового runtime. «и др.» в спеке их покрывает. `social_drive` — единственный драйв, который кладётся обратно.

Вкладка NOWA инспектора рисует affect curiosity, энергию, `social_drive` и пять полос нейромодуляторов. Автономные драйвы `curiosity` / `exploration` она не рисует. Affect curiosity хранится как `affect.boredom`, а `ChinchillaAgent.boredom` — это `1 - curiosity_level`, поэтому ось проходит round-trip. У этого детёныша остались `0.31` / `0.69`. Фраза спеки про ось curiosity, разошедшуюся с `1 - boredom`, на этом классе не проявляется.

Игрок может заметить короткую паузу, пока драйвы снова не пересекут порог, а не забытый темперамент. Голое накопление в `DriveRule` — `0.020` за симулированную секунду для curiosity и `0.011` для exploration (`src/autonomous_organism.py`), без члена affect.

| Геном | Зазор до порога | Сим-время на голой скорости |
| --- | --- | --- |
| Этот детёныш, curiosity `0.05` → порог `0.30` | 0.25 | 12.5 s |
| Этот детёныш, exploration `0.35` → порог runtime `0.48` | 0.13 | 11.8 s |
| Дефолты реестра, curiosity `0.18` → `0.45` | 0.27 | 13.5 s |
| Дефолты реестра, exploration `0.12` → `0.48` | 0.36 | 32.7 s |

На 1x это короткая пауза. На 10x — несколько секунд wall clock. Decay, пороги и half-life остаются на генах. Это один помёт и один интервал 60 s, не серия.

Файл до #65 заметнее на нейрополосах: прожитый cortisol `0.44` загрузился как `0.05`, потому что в старой схеме нет `neuromodulator_levels`. Новые сохранения пять значений держат.

## Дефекты

Блокеров, critical, major и minor нет.

## Готовность к выпуску

**С задокументированной оговоркой про драйвы.** Критерии приёмки спеки выполнены: геном применяется заново, энергия / `social_drive` / уровни нейромодуляторов возвращаются, meta проходит round-trip, старые файлы грузятся. Целевые тесты зелёные. CI на `fac946f` зелёный. Эта записка PR не мержит.

## Вопросы / блокеры

Блокеров нет.

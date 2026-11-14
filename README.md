# NOWA-Cognitive

**An AI agent that sleeps, feels, and inherits a genome — and learns without backprop.**

[![License: PolyForm Strict 1.0.0](https://img.shields.io/badge/license-PolyForm%20Strict%201.0.0-1f6feb)](https://polyformproject.org/licenses/strict/1.0.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![tests](https://img.shields.io/github/actions/workflow/status/burlakovmb/NOWA-Bio-Inspired-AI/tests.yml?branch=main&label=tests)](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/actions/workflows/tests.yml)

Source-available, not open source. Free for research and other non-commercial use under the [PolyForm Strict License 1.0.0](https://polyformproject.org/licenses/strict/1.0.0). Redistribution, modification, and commercial use need a separate license from the author ([@burlakovmb](https://github.com/burlakovmb)).

<p align="center">
  <img src="Docs/media/en/colony.gif" alt="Six NOWA agents in the chinchilla colony, each with its own memory, moving through a shared cage" width="760">
</p>

### Why it's interesting

- **It sleeps.** While awake the core writes only a bounded, decaying **labile** layer (fast bias on Q and Go/NoGo). **Stable** memory — values, habits, channels, cortex, slow affect — changes only in `Agent.sleep()`.
- **No backprop, no global loss.** Learning is local reward-prediction error on effective (stable + labile) values. Neuromodulators scale state and replay; stable writers are gated (`learning_guard`).
- **It has a body of feelings and a genome.** An 8-dimensional affect vector biases action. Offspring inherit module coefficients, and a bounded epigenome of traces that already consolidated.
- **Same mind, different bodies.** A chinchilla colony, a tamagotchi, a virtual company, and a check against published word-emotion norms. Tools are organs. Risky writes wait for a person. No language model in the loop.

### Quickstart in 60 seconds

The cognitive core is the Python standard library. From a clean clone, no packages to install. On Windows, use `python` or `py -3` wherever this page says `python3`.

```bash
python3 tools/sixty_seconds.py
```

That wakes one agent, shows the affect vector and the five neuromodulators, sleeps once, then breeds a child genome.

A colony, still with no extra packages:

```bash
PYTHONPATH="Demo/Colony chinchillas/src" python3 -m colony_gui --headless --agents 4 --duration 2
```

The full test suite (GUI tests skip when Tk or a display is missing):

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m pytest -q
```

Visual demos. `requirements-dev.txt` already includes them; otherwise `pip install -r requirements-demo.txt`. With the virtualenv still active:

```bash
# Colony window. It runs until you close it.
# Headless Linux can still draw a frame with SDL_VIDEODRIVER=dummy; omit that on a desktop.
PYTHONPATH="Demo/Colony chinchillas/src" python -m colony_gui --agents 6

# One chinchilla, pygame. Runs until you close the window.
python "Demo/Tamagochi Chinchilla/src/main.py"
```

The clips above were captured headlessly (`SDL_VIDEODRIVER=dummy`) from those demos. Regenerate both languages with `python tools/render_promo_media.py` (also needs `pillow`). The evolution frames below are `python tools/render_evolution_media.py`.

Demo windows and the core observation window open in English. `NOWA_LANG=ru` or `--lang ru` switches the language; `--lang` wins over the environment variable. In the colony and tamagotchi windows, press `G` or the separate EN and RU buttons. The active language is highlighted. The core window (`python src/gui.py`), the virtual-company labs, and the Warriner dashboard use the same EN and RU buttons. The labs also remember the choice, and `--lang` overrides that preference for the session. The core window does not store a language preference.

| Colony | Tamagotchi | Family tree |
|---|---|---|
| ![Colony still](Docs/media/en/colony.png) | ![Tamagotchi](Docs/media/en/tamagotchi.gif) | ![Lineage](Docs/media/en/lineage.png) |

The family tree is the colony lineage overlay: founders, offspring, living agents in color, dead agents in grey.

<a id="evolution-in-action"></a>

### Evolution in action

One colony, generator seed 11, three birth waves through the colony runner. Display names are the colony ids (`G0A1SF` and the rest). The status strip is five checkpoints of that run: 8 founders, then 15, 20, and 25 living, then 22 after three founder deaths (17 births, 3 deaths).

![Colony status over the run](Docs/media/en/evolution-colony.gif)

Final frame of that strip: 22 living, 17 births, 3 deaths.

![Final colony status](Docs/media/en/evolution-colony.png)

The same pedigree in the lineage overlay. Living nodes are colored, dead founders are grey, and the clip moves the tooltip across the tree.

| Tree | Tooltip moving across the tree |
|---|---|
| ![Four-generation lineage](Docs/media/en/evolution-lineage.png) | ![Lineage clip](Docs/media/en/evolution-lineage.gif) |

Swarm analytics on the final colony: the current slice, per-generation bars, gene tracks, and the forecast.

| State | Generations |
|---|---|
| ![Swarm state](Docs/media/en/evolution-swarm.png) | ![Generation bars](Docs/media/en/evolution-generations.png) |
| ![Gene tracks](Docs/media/en/evolution-genomes.png) | ![Forecast](Docs/media/en/evolution-forecast.png) |

Genome tab for a living founder and for `G3A1SF`, a generation-3 descendant. The descendant lists parents back to the founders. The third frame is that same descendant scrolled to gene changes: each figure is the child's value minus the parental midpoint, the shift introduced by crossover and mutation. Those shifts are the genome the birth path copied into the offspring. A bounded set of traces already consolidated can pass as well; that contract is [Docs/SPEC_B_EpigenomeSnapshot.en.md](Docs/SPEC_B_EpigenomeSnapshot.en.md).

| Founder `G0A4SM` | Descendant `G3A1SF` |
|---|---|
| ![Founder genome](Docs/media/en/evolution-founder.png) | ![Descendant genome](Docs/media/en/evolution-descendant.png) |

![Gene changes from the parental midpoint](Docs/media/en/evolution-mutations.png)

[English](#en) · [Русский](#ru)

<a id="en"></a>

## English

A cognitive architecture for an autonomous agent, with separate waking and sleep phases, a canonical eight-dimensional affective space, local learning from reward-prediction error, and evolutionary tuning of module parameters.

### Overview

NOWA is a software model of an agent that lives through time. While awake it records what happened and chooses an action. In sleep it consolidates slow memory and updates the channels that admit action. In the preprint the name expands to Neural Networks with Reward-Based Learning and Evolutionary Architecture Growth. This repository is that architecture, together with four experimental platforms that place the same core in different bodies.

The subject is a long-lived agent in a changing environment: which traces survive consolidation, how memory, affect and habit compete, and why a particular action was admitted. Static recognition and text generation lie outside that subject. Action selection, and the assembly of parameters for an external organ, proceed without a language model.

The organisation follows from that subject. There is no single differentiable loss over all parameters. Behaviour arises as the competition of pressures from memory, affect, habit and an admission gate that may withhold the proposed action. Waking stays separate from consolidation, so slow memory is rewritten in sleep, after the episode is fixed. Updates are local. Neuromodulators scale plasticity, and learning follows reward-prediction error. Inheritable coefficients of the modules are encoded in a genome. A bounded set of traces already consolidated may pass to offspring as an epigenome. The cognitive core works with context tokens, action channels and affective state. A write into an external system passes through an admission circuit. Drives, energy and hard limits on inner simulation bound how far autonomy extends.

The same core is applied in four settings. They differ in body and in the question a run is meant to answer.

- An ecological colony, in which social ties, generational turnover and the distribution of resource emerge from individual lives.
- A single ethological agent, with continuous visualisation of behaviour.
- A virtual organisation: a procurement sandbox, and then the same scheme of organ, decision, admission and sleep on the tools of an external server.
- A comparison of affective response with published lexical norms.

### Areas of practical application

The four platforms in `Demo/` are experimental bodies. The same scheme — a mind, a body, an admission circuit and a sleep cycle — is meant for a place where the agent stays, accumulates episodes, and writes into an external world only through admission.

**A post inside a working information system.** Tools of an external server become organs: reading is a sense, writing is a muscle. The role is data. The employee is one mind to which that role is given. Money, permissions and organisational limits stay in the body, outside the cognitive circuit. A high-risk write and an irreversible operation wait for confirmation from outside. What should come of this is a durable post: across many cycles the traces that paid off remain, the rest are dropped in sleep, and an observer can see why an action was admitted. Procurement is the worked example. The same host fits any repeating operational role whose world is a set of tools with a schema — supply, stock, dispatch, an internal desk.

**A sandbox before the live system.** The mind meets demand, failures and limits in a controlled world first. What should come of this is a policy already shaped by consequences. The same mind then moves onto the live tools, and the core stays as it is. The early mistakes stay in the sandbox.

**A population in a shared world.** Many minds, each with its own memory, and no central dispatcher. Pressure comes from the environment. What should come of this is a structure nobody assigned: ties, turnover, shortage, and the risk of collapse when a window narrows. The place is a laboratory of emergence — ecology, a group under load, a network of resources. A run answers the question of what structure arose on its own.

**One persistent creature.** A body with drives, a behavioural repertoire and a session that continues. What should come of this is behaviour that can be watched over a long stretch: need, affect and habit stay visible, and the life itself is the subject. The place is an exhibit, a setting of care or training, or an ethological study of a single agent.

**A body in the physical world.** A robot, a machine, or a mechanism is the same scheme of embodiment. The world is a continuous place, and the life cycle runs without waiting for an external task tick. A sensor reading is a sense. A command to an actuator is a muscle. The mind chooses a channel. The body assembles the command from the schema of the mechanism, the proprioceptive state, and weights derived from affect. Kinematics, the servo loop, collision geometry, and hard interlocks stay in the body, as money and permissions stay in the body of an employee. A homeostatic limit — charge, heat, mechanical load — may cancel a chosen action under critical need, as hunger and fatigue do in the colony. A high-risk or irreversible motion waits for confirmation from outside. Sleep is a separate interval, while the mechanism is idle or docked: slow memory is consolidated then.

What should come of this is a machine that remains and keeps learning. Across a long life the traces that paid off on this route, in this workshop, or on this terrain remain, and the rest are dropped in sleep. An observer can see why a motion was admitted. A fleet is a population: each machine keeps its own memory, and the environment supplies the pressure. The early life belongs in a sandbox, physical or simulated, before the same mind is placed in the working mechanism. The present platforms in this repository are simulated bodies. The physical placement uses the slot already occupied by the protocol body and by the organism: a mind, a body, admission, and sleep.

The comparison with lexical norms is a bench, not a home. It checks that an affective shift lines up with published human norms. A quantitative result on a business task is not fixed by this text. It is produced by a run of the particular platform.

Observers, panels and fitness reports read the agent. They do not change its policy. Individuals in a population keep separate memories and receive no command from a central dispatcher.

Scientific description of the complex: [Docs/SCIENTIFIC_DESCRIPTION.en.md](Docs/SCIENTIFIC_DESCRIPTION.en.md).  
Formalisation and relation to the literature: [Docs/arxiv_NOWA_en.md](Docs/arxiv_NOWA_en.md).  
Document index: [Docs/INDEX.en.md](Docs/INDEX.en.md).  
Reading order: [Docs/START_HERE_NEW.en.md](Docs/START_HERE_NEW.en.md).

### Subject

During waking the agent records episodes, activates memory, and selects an action using stable plus labile effective values. The host passes elapsed time (`dt` or `advance_time`) and calls `sleep()` when its schedule requires consolidation; stable parameters do not change between sleeps. Neuromodulators modulate state and sleep replay. The genome encodes inheritable coefficients of the subsystems; the epigenome carries a bounded set of traces already consolidated. Host contract and plasticity parameters: [Docs/architecture/two-tier-plasticity.en.md](Docs/architecture/two-tier-plasticity.en.md). Agent persistence is UTF-8 JSON (`.nowa`), not pickle; see [Docs/specs/issue-16-31-safe-agent-state.en.md](Docs/specs/issue-16-31-safe-agent-state.en.md). Legacy `.pkl` saves must be recreated. The cognitive core does not import the protocol of external tools.

### Repository layout

| Directory | Contents |
|---|---|
| `src/` | Cognitive core, autonomous organism, external interaction layer, platform body, genome, and swarm environment |
| `tests/` | Regression checks of the core |
| `Docs/` | Scientific exposition, preprint, and normative phase specifications |
| `Demo/Colony chinchillas/` | Multi-agent ecological colony |
| `Demo/Tamagochi Chinchilla/` | Ethological agent with continuous visualisation |
| `Demo/Virtual company/` | Procurement sandbox, protocol body, and employee host |
| `Demo/Warriner Validation/` | Comparison of affective response with lexical norms |

### Reproduction

```bash
python3 -m venv .venv
```

Activate the environment in Windows PowerShell with `.venv\Scripts\Activate.ps1`.  
On macOS and Linux: `source .venv/bin/activate`.  
If the `python3` command is named `python` on your machine, use that.

Install test dependencies, then run the full suite. Tests that open a Tk window are skipped when Tk or a display is unavailable.

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Core observation interface:

```bash
python src/gui.py
```

`--lang en|ru` and `NOWA_LANG` select the language. EN and RU in the title bar switch it, and the active button is highlighted.

![NOWA cognitive interface in English](Docs/media/en/core-gui.png)

The inspector opens from Actions:

![Agent state inspector in English](Docs/media/en/core-inspector.png)

Subsystem verification protocols are given in [Docs/TESTING.en.md](Docs/TESTING.en.md). Platform commands are given in the English scientific accounts linked from [Docs/INDEX.en.md](Docs/INDEX.en.md).

### Reading

The English links above stay in English. The Russian text of the same documents is a separate file, linked from the top of each English page. [Docs/INDEX.en.md](Docs/INDEX.en.md) lists every English document in `Docs/` and in `Demo/*/Docs/`. Normative phase specifications are required when a module contract is changed. Laboratory reports of phase completion preserve the history of development and do not define the current state of the complex.

### License

Source-available, not open source. Licensed under the [PolyForm Strict License 1.0.0](https://polyformproject.org/licenses/strict/1.0.0); the full text is in [LICENSE](LICENSE).
Research and other noncommercial use are permitted under the terms of the license.
The public license does not allow redistribution or derivative works.
Modification, redistribution and any commercial use require a separate commercial license from the author.
Commercial licensing: GitHub [@burlakovmb](https://github.com/burlakovmb).
If you use this in research, see [CITATION.cff](CITATION.cff).

### Contributing / Участие

Contributions are accepted only by individual invitation from Mikhail Burlakov, the Author and Owner of this repository. If invited, contribute via a public fork and pull request. Your contribution is governed by [CONTRIBUTOR_LICENSE.md](CONTRIBUTOR_LICENSE.md). The project’s source code remains licensed under [PolyForm Strict License 1.0.0](https://polyformproject.org/licenses/strict/1.0.0); see [LICENSE](LICENSE).

Участие возможно только по индивидуальному приглашению от Михаила Бурлакова как Автора и Владельца данного репозитория. Приглашённым контрибьюторам следует работать через публичный форк и pull request. Условия участия заданы в [CONTRIBUTOR_LICENSE.md](CONTRIBUTOR_LICENSE.md). Исходный код проекта по-прежнему распространяется по [PolyForm Strict License 1.0.0](https://polyformproject.org/licenses/strict/1.0.0); полный текст — в [LICENSE](LICENSE).

---

<a id="ru"></a>

## Русский

**Агент, который спит, чувствует и наследует геном — и учится без обратного распространения ошибки.**

Исходный код доступен, это не открытая лицензия. Исследовательское и иное некоммерческое использование — по [PolyForm Strict License 1.0.0](https://polyformproject.org/licenses/strict/1.0.0). Распространение, изменение и коммерческое использование требуют отдельной лицензии автора ([@burlakovmb](https://github.com/burlakovmb)).

Короткий прогон без дополнительных пакетов — те же команды, что в английском блоке «Quickstart in 60 seconds» выше: `python tools/sixty_seconds.py`, затем колония в headless-режиме. Полный набор тестов: `pip install -r requirements-dev.txt` и `python -m pytest -q`. Тесты графического интерфейса пропускаются, если нет Tk или дисплея.

Окна демо и окно наблюдения ядра по умолчанию на английском. `NOWA_LANG=ru` или `--lang ru` переключают язык (`--lang` важнее переменной окружения). В колонии и тамагочи — клавиша `G` или отдельные кнопки EN и RU. Активный язык подсвечен. В окне ядра (`python src/gui.py`), в лабораториях виртуальной компании и на панели Warriner те же кнопки EN и RU. Лаборатории запоминают выбор, а `--lang` перекрывает его на этот запуск. Окно ядра язык не запоминает.

| Колония | Тамагочи | Родословная |
|---|---|---|
| ![Колония](Docs/media/ru/colony.png) | ![Тамагочи](Docs/media/ru/tamagotchi.gif) | ![Родословная](Docs/media/ru/lineage.png) |

Родословная — оверлей колонии: основатели, потомки, живые в цвете, умершие серым.

<a id="evolyutsiya-v-deystvii"></a>

### Эволюция в действии

Одна колония, зерно генератора 11, три волны рождений через бегунок колонии. Имена на экране — идентификаторы колонии (`G0A1SF` и далее). Полоса состояния — пять срезов этого прогона: 8 основателей, затем 15, 20 и 25 живых, затем 22 после смерти трёх основателей (17 рождений, 3 смерти).

![Состояние колонии по ходу прогона](Docs/media/ru/evolution-colony.gif)

Последний кадр этой полосы: 22 живых, 17 рождений, 3 смерти.

![Финальное состояние колонии](Docs/media/ru/evolution-colony.png)

Та же родословная. Живые узлы цветные, умершие основатели серые, ролик ведёт подсказку по дереву.

| Дерево | Подсказка по дереву |
|---|---|
| ![Родословная четырёх поколений](Docs/media/ru/evolution-lineage.png) | ![Ролик родословной](Docs/media/ru/evolution-lineage.gif) |

Аналитика роя на финальной колонии: текущий срез, столбцы по поколениям, треки генов и прогноз.

| Состояние | Поколения |
|---|---|
| ![Состояние роя](Docs/media/ru/evolution-swarm.png) | ![Столбцы поколений](Docs/media/ru/evolution-generations.png) |
| ![Треки генов](Docs/media/ru/evolution-genomes.png) | ![Прогноз](Docs/media/ru/evolution-forecast.png) |

Вкладка «Геном» у живого основателя и у `G3A1SF`, потомка третьего поколения. Потомок перечисляет родителей до основателей. Третий кадр — тот же потомок, прокрученный к изменениям генов: каждая величина есть значение ребёнка минус середина родителей, сдвиг от кроссовера и мутации. Эти сдвиги — геном, который путь рождения скопировал потомку. Ограниченный набор уже консолидированных следов тоже может перейти; этот контракт описан в [Docs/SPEC_B_EpigenomeSnapshot.ru.md](Docs/SPEC_B_EpigenomeSnapshot.ru.md).

| Основатель `G0A4SM` | Потомок `G3A1SF` |
|---|---|
| ![Геном основателя](Docs/media/ru/evolution-founder.png) | ![Геном потомка](Docs/media/ru/evolution-descendant.png) |

![Изменения генов относительно середины родителей](Docs/media/ru/evolution-mutations.png)

Когнитивная архитектура автономного агента с раздельными фазами бодрствования и сна, каноническим восьмимерным аффективным пространством, локальным обучением по ошибке предсказания награды и эволюционной настройкой параметров модулей.

### Обзор

NOWA — программная модель агента, который живёт во времени. В бодрствовании он записывает произошедшее и выбирает действие. Во сне консолидирует медленную память и обновляет каналы, которыми действие допускается. В препринте имя раскрывается как Neural Networks with Reward-Based Learning and Evolutionary Architecture Growth: нейронные сети с обучением по награде и эволюционным ростом архитектуры. Репозиторий содержит эту архитектуру и четыре экспериментальные установки, которые помещают одно и то же ядро в разные тела.

Это платформа для долгоживущих агентов в изменяющейся среде: какие следы переживут консолидацию, как конкурируют память, аффект и привычка и почему было допущено именно это действие. Статическое распознавание и порождение текста лежат вне этого предмета. Выбор действия и сборка параметров внешнего органа обходятся без языковой модели.

Единой дифференцируемой функции потерь по всем параметрам нет. Поведение возникает как конкуренция давлений памяти, аффекта, привычки и допуска, который может удержать предложенное действие. Бодрствование отделено от консолидации: медленная память переписывается во сне, после того как эпизод зафиксирован. Обновления локальны. Нейромодуляторы масштабируют пластичность, обучение идёт по ошибке предсказания награды. Наследуемые коэффициенты модулей кодирует геном. Ограниченный набор уже консолидированных следов может перейти потомству как эпигеном. Когнитивное ядро работает с контекстными токенами, каналами действия и аффективным состоянием. Запись во внешнюю систему проходит через контур допуска. Побуждения, энергия и жёсткие пределы внутренней симуляции ограничивают автономность.

Одно и то же ядро применяется в четырёх постановках. Они различаются телом и вопросом, на который отвечает прогон.

- Экологическая колония, в которой социальные связи, смена поколений и распределение ресурса возникают из жизней отдельных особей.
- Один этологический агент с непрерывной визуализацией поведения.
- Виртуальная организация: песочница закупок, а затем та же схема «орган — решение — допуск — сон» на инструментах внешнего сервера.
- Сопоставление аффективного отклика с опубликованными лексическими нормами.

### Области практического применения

Четыре установки в `Demo/` — экспериментальные тела. Та же схема — ум, тело, контур допуска и цикл сна — рассчитана на место, где агент остаётся, копит эпизоды и пишет во внешний мир только через допуск.

**Должность в действующей информационной системе.** Инструменты внешнего сервера становятся органами: чтение — сенсор, запись — мышца. Роль задаётся данными. Сотрудник — один ум, которому эта роль выдана. Деньги, права и организационные пределы лежат в теле, вне когнитивного контура. Запись высокого риска и необратимая операция ждут подтверждения извне. По идее получается долговременная должность: за много циклов остаются следы, которые оправдались, остальное отсеивается во сне, и наблюдатель видит, почему действие было допущено. Закупки — разобранный пример. Тот же хост подходит любой повторяющейся операционной роли, чей мир есть набор инструментов со схемой: снабжение, запас, диспетчеризация, внутренний пост.

**Песочница до живой системы.** Сначала ум встречает спрос, срывы и пределы в управляемом мире. По идее получается политика, уже сформированная последствиями. Затем тот же ум переносится на живые инструменты, ядро при этом остаётся прежним. Ранние ошибки остаются в песочнице.

**Популяция в общем мире.** Много умов, у каждого своя память, центрального диспетчера нет. Давление задаёт среда. По идее получается устройство, которого никто не назначал: связи, смена состава, дефицит и риск схлопывания, когда окно сужается. Место — лаборатория возникновения: экология, коллектив под нагрузкой, сеть ресурсов. Прогон отвечает на вопрос, какое устройство возникло само.

**Одна длящаяся особь.** Тело с побуждениями, поведенческим репертуаром и сессией, которая продолжается. По идее получается поведение, которое можно смотреть долго: нужда, аффект и привычка остаются видны, и предметом является сама жизнь. Место — экспозиция, обстановка ухода или обучения, этологическое наблюдение одного агента.

**Тело в физическом мире.** Робот, машина или механизм — та же схема воплощения. Мир здесь непрерывен, и жизненный цикл идёт, не дожидаясь внешнего такта задачи. Показание датчика — сенсор. Команда приводу — мышца. Ум выбирает канал. Тело собирает команду из схемы механизма, проприоцептивного состояния и весов, производных от аффекта. Кинематика, сервоконтур, геометрия столкновений и жёсткие блокировки остаются в теле. Гомеостатический предел — заряд, нагрев, механическая нагрузка — может отменить выбранное действие при критической нужде, как голод и усталость в колонии. Движение высокого риска и необратимое движение ждут подтверждения извне. Сон — отдельный промежуток, пока механизм простаивает или стоит на базе: тогда консолидируется медленная память.

По идее получается машина, которая остаётся и продолжает учиться. За долгую жизнь сохраняются следы, оправдавшиеся на этом маршруте, в этом цехе или на этой местности, остальное отсеивается во сне. Наблюдатель видит, почему движение было допущено. Парк машин — популяция: у каждой своя память, давление задаёт среда. Ранняя жизнь проходит в песочнице, физической или смоделированной, и лишь затем тот же ум сажается в рабочий механизм. Нынешние установки репозитория — смоделированные тела. Физическое место занимает ту же ячейку, что протокольное тело и организм.

Сопоставление с лексическими нормами — стенд, а не место жительства. Оно проверяет, что сдвиг аффекта сопоставим с опубликованными человеческими нормами. Количественный результат хозяйственной задачи этим текстом не задаётся. Его даёт прогон конкретной установки.

Наблюдатели, панели и отчёты о приспособленности читают агента и политику его не меняют. Особи популяции хранят память раздельно и не получают команду от центрального диспетчера.

Научное описание комплекса: [Docs/SCIENTIFIC_DESCRIPTION.ru.md](Docs/SCIENTIFIC_DESCRIPTION.ru.md).  
Формализация и сопоставление с литературой: [Docs/arxiv_NOWA_ru.md](Docs/arxiv_NOWA_ru.md).  
Указатель документов: [Docs/INDEX.ru.md](Docs/INDEX.ru.md).  
Порядок чтения: [Docs/START_HERE_NEW.ru.md](Docs/START_HERE_NEW.ru.md).

### Предмет

В бодрствовании агент записывает эпизоды, активирует память и выбирает действие по эффективным (стабильным + лабильным) значениям. Хост передаёт прошедшее время (`dt` или `advance_time`) и вызывает `sleep()` по своему расписанию; стабильные параметры между снами не меняются. Нейромодуляторы модулируют состояние и replay во сне. Геном кодирует наследуемые коэффициенты подсистем; эпигеном переносит ограниченный набор уже консолидированных следов. Контракт с хостом: [Docs/architecture/two-tier-plasticity.ru.md](Docs/architecture/two-tier-plasticity.ru.md). Когнитивное ядро не импортирует протокол внешних инструментов.

### Состав репозитория

| Каталог | Содержание |
|---|---|
| `src/` | Когнитивное ядро, автономный организм, слой внешнего взаимодействия, платформенное тело, геном и роевая среда |
| `tests/` | Регрессионные проверки ядра |
| `Docs/` | Научное изложение, препринт и нормативные спецификации фаз |
| `Demo/Colony chinchillas/` | Многоагентная экологическая колония |
| `Demo/Tamagochi Chinchilla/` | Этологический агент с непрерывной визуализацией |
| `Demo/Virtual company/` | Песочница закупок, протокольное тело и хост сотрудников |
| `Demo/Warriner Validation/` | Сопоставление аффективного отклика с лексическими нормами |

### Воспроизведение

```bash
python3 -m venv .venv
```

Активация среды в Windows PowerShell: `.venv\Scripts\Activate.ps1`.  
В macOS и Linux: `source .venv/bin/activate`.  
Если команда называется `python`, а не `python3`, используйте её.

Установите зависимости тестов и запустите полный набор. Тесты, которым нужно окно Tk, пропускаются, если Tk или дисплей недоступны.

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Интерфейс наблюдения ядра:

```bash
python src/gui.py
```

`--lang en|ru` и `NOWA_LANG` задают язык. Кнопки EN и RU в заголовке переключают его, активная подсвечена.

![Когнитивный интерфейс NOWA по-русски](Docs/media/ru/core-gui.png)

Инспектор открывается из блока «Действия»:

![Инспектор состояния агента по-русски](Docs/media/ru/core-inspector.png)

Протоколы проверки подсистем приведены в [Docs/TESTING.ru.md](Docs/TESTING.ru.md). Команды установок — в русских научных описаниях, на которые ведёт [Docs/INDEX.ru.md](Docs/INDEX.ru.md).

### Чтение

Русские ссылки выше остаются в русских файлах. Английский текст тех же документов вынесен отдельно и указан в начале каждой русской страницы. [Docs/INDEX.ru.md](Docs/INDEX.ru.md) перечисляет каждый русский документ в `Docs/` и в `Demo/*/Docs/`. Нормативные спецификации фаз требуются при изменении контракта модуля. Лабораторные отчёты о завершении фаз сохраняют историю разработки и не задают актуальное состояние комплекса.

### Лицензия

Исходный код доступен; это не открытая (open source) лицензия. Проект распространяется по лицензии [PolyForm Strict License 1.0.0](https://polyformproject.org/licenses/strict/1.0.0); полный текст — в файле [LICENSE](LICENSE).
Исследовательское и иное некоммерческое использование разрешено на условиях лицензии.
Публичная лицензия не разрешает распространение и производные произведения.
Изменение, распространение и любое коммерческое использование требуют отдельной коммерческой лицензии от автора.
По вопросам коммерческого лицензирования: GitHub [@burlakovmb](https://github.com/burlakovmb).
Для научного цитирования: [CITATION.cff](CITATION.cff).

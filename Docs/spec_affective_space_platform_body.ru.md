# Спецификация: AffectiveSpace как канон платформы + MCP-тело без MotorAdapter

English version: [spec_affective_space_platform_body.en.md](spec_affective_space_platform_body.en.md)

**Статус (27 сентября 2026 г.).** Документ ядра. Актуальное научное изложение комплекса на русском и английском языках приведено в [SCIENTIFIC_DESCRIPTION.ru.md](SCIENTIFIC_DESCRIPTION.ru.md). Текст ниже сохраняет формулировки исходной редакции: это нормативный контракт модуля либо лабораторная запись.

**Версия:** 1.1  
**Статус:** Готово к реализации — документ для передающего агента  
**Дата:** 2026-08-24  
**Патч 1.1:** оси A(t) заморожены навсегда в этой спецификации; реальный 1С — тот же контракт transport, не особый случай; LLM не участвует в теле.  
**Аудитория:** агент-исполнитель (менять код строго по этому тексту)  
**Платформа (источник истины ядра):** `src/`  
**Текущий слой тела (Demo, подлежит универсализации):** `Demo/Virtual company/src/nowa_body/`

Связанные документы (не переписывать, только согласовать):

- `src/affective_space.py` — as-built канон A(t)
- `Docs/affective_core_phase4_spec.md`
- `Docs/spec_per_axis_affective_decay.md`
- `Demo/Virtual company/Docs/NOWA_Body_Layer_Phase1_AsBuilt_MCP_API.md`
- `Demo/Virtual company/Docs/NOWA_Body_Layer_Phase1_Spec.md`

---

## 0. Задание исполнителю (читать первым)

Сделать два связанных изменения архитектуры:

1. **Полное покрытие платформы NOWA каноническим `AffectiveSpace`.**  
   Один вектор A(t) — единственный источник аффективного состояния. Каждый модуль в `src/`, который сегодня читает `affect_state`, параллельный VAD, «stress» из другого места или не читает аффект вообще при принятии решений, получает явный контракт: **читает A(t) / `decision_bias()` / пишет `EmotionalImpulse`**, либо явно помечен как аффект-слепой (инфраструктура данных).

2. **Убить концепт MotorAdapter как точку расширения.**  
   Роль больше не пишется как Python-адаптер «action_type → params под 1С».  
   Контракт тела: **прописал MCP-сервер → получил tools/list → тулы стали органами → разум NOWA управляет органами.**  
   Параметры вызова собираются универсально из JSON Schema тула + WorldState + A(t), без доменного Python.

Исполнитель **не** добавляет оси в A(t) (ни `urgent`, ни `budget`, ни любые другие), **не** добавляет второй эмоциональный контейнер, **не** зовёт MCP из `Agent.step`, **не** использует языковую модель для сборки параметров тула.

---

## 1. Проблема as-built

### 1.1 AffectiveSpace уже канон, покрытие — нет

В `src/affective_space.py` канон уже есть:

```
AXES = (valence, arousal, dominance, stress, trust, curiosity, stability, attachment)
range: [-1, 1]
A(t+1) = baseline + axis_decay*(A-baseline) + Σ impulses − λ*(A-baseline)  [+ optional legacy]
decision_bias() → {risk, response_speed, word_choice, empathy, goal_priority}
```

`Agent.affective_space` — runtime source of truth. `affect_state` — проекция.

Разрывы покрытия (исправлять):

| Разрыв | Факт |
|---|---|
| Двойной контур | `emotional_regulation.py` держит свой valence/arousal и **не** является I/O к A(t) |
| Семантика на legacy | `semantic_emotions.py` считает аттракторы по `legacy_axes_snapshot()`, не по канону |
| Селектор | `selector.py` берёт скаляр `affect_modifier`, игнорирует вектор `decision_bias` |
| BG | aversive почти только `stress`; не использует `risk` / `trust` / `curiosity` |
| Сон | `sleep.py` не модулирует decay/шум A(t) |
| Память | гиппокамп не обязан хранить `EmotionalTrace` с эпизодом |
| Тело | encoder пишет токены; READ почти не делает `affective_space.step` |
| Outcome mapping | `encode_action_outcome` отдаёт смесь valence/arousal/trust/stress — неполный канон, плюс ключи не всегда совпадают с `AXES` |
| GUI / self_model | часть панелей всё ещё от `affect_state` |

### 1.2 Почему MotorAdapter нельзя масштабировать

As-built пайплайн:

```
action_type (словарь роли: place_order_cheap_supplier, …)
    → MotorAdapter.resolve
        → capability_for_action(action_type)   # параллельный словарь
        → _build_params(...)                   # NotImplemented / роль-класс
    → ProposedAction(tool_id, params)
```

Это ломается на каждом новом MCP:

- у каждого сервера свой набор tools и JSON Schema;
- `action_types` на capability — второй язык, который надо руками клеить к BG-каналам;
- `_build_params` в `ProcurementBodyMotorAdapter` знает поставщиков, coverage days, стратегии — это **не тело**, это спрятанный доменный мозг;
- `register_from_mcp_discovery` — `NotImplementedError`;
- `event_classifier` — ещё один Python на роль.

Владелец платформы: *прописал MCP server — получил тулы — разум управляет тулами как телом.*

MotorAdapter этому противоречит. Его нет в целевой архитектуре.

---

## 2. Принципы (нарушать нельзя)

**P1. Один аффект.** Только `AffectiveSpace.axes`. Любой другой контейнер — проекция или интерпретация (read-only).

**P2. Импульсы, не присваивание.** Внешний мир и память меняют A(t) через `EmotionalImpulse` (`source ∈ {external, memory, internal}`) и `AffectiveSpace.step(...)`. Запрещено `axes["stress"] = 1.0` из хоста/тела.

**P3. Разум не знает MCP.** `Agent.step` / selector / BG не импортируют MCP SDK. Они видят: context tokens, action channels (`tool_id` или `wait_and_monitor`), A(t).

**P4. Тул = орган.** После discovery каждый tool — `MCPCapability`. READ = сенсор. WRITE = мышца. `tool_id` формата `mcp__<server>__<tool_name>` **и есть** action channel базальных ганглиев.

**P5. Нет роль-классов мышц.** Запрещены subclasses MotorAdapter, запрещён `motor_adapter: pkg.mod:Class` в YAML как обязательный механизм. Допустима только **декларативная** подсказка (JSONPath / field aliases) в YAML, одинаковая для любого сервера.

**P6. Approval снаружи.** HIGH_WRITE / IRREVERSIBLE не обходятся A(t). Стресс не отключает `ApprovalGate`.

**P7. Обучение во сне.** Waking body: `decision_only=True`, store эпизода после известного исхода. Path иммутабелен, ровно один `EventType.ACTION`.

**P8. Деньги не валентность. Срочность не ось.**  
Стоимость / бюджет / остаток — скаляры `WorldState` и признаки ranking (`cost`, `quantity`).  
Срочность — уже существующие `arousal` / `stress` + `rank_weights().speed_seek`.  
**Новых осей A(t) не будет.** Канон `AXES` из восьми имён закрыт.

**P9. Без проекции чувств.** Операционные числа и токены. Никакого «агент грустит» как управляющего сигнала.

**P10. Универсальность проверяется будущим 1С, не Mock.**  
Эта поставка может ходить в MockMCP. Когда появится реальный 1С MCP, он обязан встать **только** как ещё один `MCPTransport` (те же `list_tools` / `call_tool`). Ноль правок `AffectiveSpace`, SchemaBinder, Agent, ranking, YAML-формы роли. Если для 1С понадобится новый Python-класс мышцы — решение не универсально, это баг спецификации.

**P11. Params собирает SchemaBinder, не «ум» снаружи.**  
Аргументы тула = JSON Schema + WorldState + lexicon/aliases + `rank_weights()`. Ни языковая модель, ни доменный код роли в этом пути не участвуют.

---

## 3. Канон AffectiveSpace (заморозить)

Файл: `src/affective_space.py`.

Состав `AXES` **заморожен**. Не добавлять оси, не переименовывать, не делать «временные» оси под домен. Без отдельного решения владельца не менять:

- состав `AXES`, диапазон [-1, 1];
- `EmotionalImpulse` / `EmotionalTrace`;
- `step(...)` уравнение и per-axis `axis_decay`;
- `decision_bias()` и `DECISION_DIMENSIONS`;
- `to_dict` / `from_dict` / storage round-trip.

Разрешённые **добавления** (не ломая сигнатуры):

| API | Зачем |
|---|---|
| `AffectiveSpace.outcome_impulse(status: str, magnitude: float = 1.0) -> EmotionalImpulse` | Универсальный маппинг MCP status → канонический вектор (см. §6.6). Не дублировать ад-хок словари в encoder. |
| `AffectiveSpace.rank_weights() -> Dict[str, float]` | Удобный readout для тела: производные веса `{cost, speed, reliability, novelty, caution}` из `decision_bias()` + осей. Чистая функция, без I/O. |

Дефолтный маппинг `rank_weights()` (все выходы clamp [-1, 1] затем нормируйте в [0, 1] для весов):

```
caution      = 0.5 + 0.5 * clamp(stress - 0.5*valence + 0.3*(1-trust))
cost_aversion = clamp(0.4 - 0.6*bias.risk + 0.4*caution)
speed_seek    = clamp(0.5 + 0.7*bias.response_speed + 0.3*max(0, arousal) - 0.2*stability)
reliability   = clamp(0.5 + 0.5*trust + 0.3*attachment - 0.4*bias.risk)
novelty_seek  = clamp(0.5 + 0.7*curiosity - 0.4*stress)
assertiveness = clamp(0.5 + 0.6*dominance + 0.3*bias.goal_priority)
```

`legacy_compat_weight` остаётся 0 по умолчанию.

---

## 4. Полное покрытие `src/` — матрица контрактов

Легенда режима:

- **R** — модуль **читает** `axes` и/или `decision_bias()` / `rank_weights()`
- **W** — модуль **пишет** только через `EmotionalImpulse` + `step` (или отдаёт impulse агенту)
- **P** — модуль **проецирует** A(t) в legacy (write в `affect_state` только из Agent)
- **I** — интерпретация (семантика, GUI), не управляет выбором
- **∅** — аффект-слепой (данные/I/O), так и должно быть
- **X** — сегодня дыра; после этой спеки обязателен R/W

Оркестратор всех W-вызовов в waking — `Agent` (и body runtime для external impulses). Модули ядра **не** вызывают MCP.

### 4.1 Когнитивный контур

| Модуль | Файл | Режим | Контракт |
|---|---|---|---|
| AffectiveSpace | `affective_space.py` | — | Канон. |
| Agent | `agent.py` | R/W/P | Единственный orchestrator `step()` A(t). После каждого когнитивного шага: derive impulses (§7), `affective_space.step`, project `affect_state`. BG aversive = f(stress, caution). Selection modifier = не один скаляр, а канал-wise из `decision_bias` (§7.2). |
| AffectiveState | `affect.py` | P | Только проекция. Запрещено `update_from_reward` как источник истины, если есть `affective_space`. GUI может читать projection. |
| ActionSelector | `selector.py` | R | `choose(..., affect_bias: Dict[str, float] \| None)`. Скаляр `affect_modifier` deprecated, оставить как fallback = `1 + 0.2*response_speed - 0.25*max(0,stress)`. Новое: per-action scale от caller (Agent), не доменная логика внутри selector. |
| BasalGanglia | `basal_ganglia.py` | R | `aversive_signal` из Agent: `max(0, stress, caution)`. Go gain ↑ `response_speed`; NoGo ↑ `caution`; exploration temperature ↑ `novelty_seek`. Не импортировать AffectiveSpace, только float/dict от Agent. |
| ThalamicGate | там же | R | Порог Go зависит от `stability` (низкая → труднее пропустить импульсивное). |
| Hippocampus | `hippocampus.py` | R/W | При `store` после исхода: `create_trace` с эпизодом. При `activate`: `recall_trace` → memory impulses в Agent.step. Не менять A(t) сам. |
| Cortex | `cortex.py` | R | Consolidation/sleep может читать `stability`/`arousal` как gain пластичности (через SleepManager). |
| IntentMemory | `intent_memory.py` | R | Привычки: reinforcement *= f(valence, threat←stress). Уже есть affect hooks — перевести на snapshot A(t), не на параллельные поля. |
| ValueLayer | `value_layer.py` | W | TD error → internal impulse: `valence += tanh(td)`, `stress += max(0,-td)`, `curiosity += |td|*novelty`. Не хранить свой аффект. |
| PredictionLayer | `prediction_layer.py` | W | Prediction error / shock → impulse stress/curiosity (малая интенсивность). |
| DecisionArbitrator | `decision_arbitrator.py` | R | Веса habitual vs deliberative: высокий `axis_conflict` + низкий `stability` → deliberative. |
| ConflictArbitration | `conflict_arbitration.py` | R/W | `raw_conflict` модулируется arousal/stress (как ACC spec). Обратно: высокий perceived conflict → internal impulse на stress/arousal. Без второго state. |
| HippocampalImagineEngine | `hippocampal_imagine_engine.py` | R | Воображаемые исходы **не** пишут A(t). Scoring траекторий: expected valence/stress из памяти + текущий `rank_weights`. |
| Deliberative planning (Agent) | `agent.py` | R | Planning temperature ↑ curiosity, ↓ stress. Risk penalty rollout *= `cost_aversion`. |
| Experience / Path | `experience.py` | ∅ | Структура данных. ACTION label = `tool_id` в body-режиме. |
| Dataset / Sample / data_loader | `dataset.py`, `sample.py`, `data_loader.py` | ∅ | |
| ActionIntent / Realizer | `action_intent.py`, `action_realizer.py` | R | NLG/выражение: `word_choice`, `empathy` из `decision_bias`. Не путать с MCP-мышцами. |

### 4.2 Аффективный стек вокруг канона

| Модуль | Файл | Режим | Контракт |
|---|---|---|---|
| AffectivePersistence | `affective_persistence.py` | R | Сигналы считать из A(t) snapshot, не из threat/curiosity `affect_state` как истины. |
| AffectiveBackground | `affective_background.py` | R | По-прежнему модификатор decay/inertia/noise для `step(background=...)`. Не задаёт оси. |
| SemanticEmotions | `semantic_emotions.py` | I | **Перевести аттракторы на канонические оси** (не pleasure/pain как primary). Legacy snapshot — только compat. Слой по-прежнему не выбирает действия. |
| EmotionalMemoryNarratives | `emotional_memory_narratives.py` | I | Читает A(t) + semantic. Не пишет оси. |
| EmotionalExpectations | `emotional_expectations.py` | R/W | Прогноз vs факт: mismatch → impulse (prediction analog). |
| EmotionalRegulation | `emotional_regulation.py` | R/W | **Запрещён параллельный VAD как source of truth.** CER либо (a) становится чистым модулятором `lambda_reg` / decay, читая A(t), либо (b) эмитит internal impulses. Свой valence больше не хранится как канон. |
| StabilityMonitoring | `stability_monitoring.py` | I | Метрики: `speed()`, `axis_conflict()`, norm vs cap. Read-only. |
| SelfModel | `self_model.py` | I | Интроспекция с `snapshot()`, не «я чувствую». |

### 4.3 Физиология, сон, обучение

| Модуль | Файл | Режим | Контракт |
|---|---|---|---|
| Neuromodulators | `neuromodulators.py` | R/W | Двусторонняя связь **через Agent**, не циклический import: DA↔valence/curiosity, 5HT↔stability/trust, NE↔arousal/stress, ACh↔curiosity/focus analog (dominance). NM не дублирует оси. |
| Wakefulness | `wakefulness.py` | R | Уже аргумент `step(wakefulness=)`. Process S не из A(t). Высокий stress может ускорять `update_waking` (коэффициент, не замена Process S). |
| Sleep | `sleep.py` | R/W | Во сне: `step(..., asleep=True, time_elapsed=<dt цикла>)` — симулированные секунды сна за цикл (`SECONDS_PER_SLEEP_CYCLE` или `sleep_duration_seconds/cycles`), `SLEEP_RECOVERY_SCALE` на клиренс/восстановление; внешние impulses ≈ 0. Replay может `recall_trace`. MCP не вызывать. См. [specs/issue-54-affect-simulated-time.ru.md](specs/issue-54-affect-simulated-time.ru.md). |
| Temporal / TemporalChains | `temporal.py`, `temporal_chains.py` | R | Логировать snapshot A(t) в T0/T1 (сейчас частично affect_state). |

### 4.4 Эволюция, популяция, организм

| Модуль | Файл | Режим | Контракт |
|---|---|---|---|
| Genome | `genome.py` | R | Гены `af_*` уже есть — маппятся в `axis_decay` / `lambda_reg` / `baseline_adapt_rate`. Добавить гены на `decision_matrix` **не** обязательно в этой поставке. |
| Epigenome | `epigenome.py` | R | Snapshot может включать `baseline` A(t) как медленный drift (опционально, не ломая формат без миграции). |
| AgentFactory | `agent_factory.py` | R | Уже применяет affective genes. Проверить, что не пишет в `affect_state` в обход space. |
| Fitness | `fitness.py` | R | Компонент affective stability: низкий `axis_conflict`, умеренный stress, не застревание у `norm_cap_max`. |
| Swarm | `swarm.py` | R/W | Уже читает axes — стандартизовать на `snapshot()`. Social signal → external impulse. Fallback `step(inputs=…)` без `time_elapsed` двигает **1,0** симулированную секунду (спека issue #54). |
| Ecology / Reproduction / Mortality | `ecology.py`, `reproduction.py`, `mortality.py` | R | Mortality/stress coupling: высокий sustained stress ↑ mortality pressure (если слой это умеет). Иначе R без W. |
| PopulationObserver | `population_observer.py` | I | Агрегировать mean axes по популяции. |
| AutonomousOrganism | `autonomous_organism.py` | R | Drives не заменяют A(t). Energy/drives могут эмитить internal impulses (arousal/stress при depletion). |
| SimulationUtility | `simulation_utility.py` | R | Utility может брать `rank_weights` как tie-breaker, не как reward. |

### 4.5 Внешний контур ядра vs тело

| Модуль | Файл | Режим | Контракт |
|---|---|---|---|
| ExternalInteractionLayer | `external_interaction_layer.py` | W | Feedback.reward → impulse через тот же `outcome_impulse`. Не параллельная «эмоция среды». Для MCP-хоста **предпочтительнее body runtime**, EIL — generic adapter. Не плодить третий путь обучения. |
| GUI | `gui.py` | I | Панель 8 канонических осей + `decision_bias` + speed/conflict. Legacy 4 бара — overlay projection. |
| Storage | `storage.py` | ∅/P | Persist `affective_space.to_dict()`. `affect_state` можно сохранять как projection, reload не имеет права перебить канон. |

---

## 5. Целевая архитектура тела: органы, не адаптеры

### 5.1 Метафора

```
MCP server(s)          = внешний мир + конечности
tools/list             = анатомия (какие органы есть)
READ tools             = интеро/экстероцепция
WRITE tools            = мышцы
WorldState             = схема тела / проприоцепция (последние сенсоры)
AffectiveSpace         = как телу «с этим» (канон)
Hippocampus + BG       = что делать этим телом
SchemaBinder           = спинной мозг: собрать позу мышцы из схемы+проприоцепции
ApprovalGate           = внешний запрет (не часть разума)
```

Разум **выбирает орган** (`tool_id`). Тело **не интерпретирует закупку**. Если не может связать schema — мышца в этом тике недоступна (`wait_and_monitor`).

### 5.2 Пайплайн (замена MotorAdapter)

```
Host
  1. connect MCP servers from role YAML
  2. tools/list → MCPOrganRegistry.register_from_discovery(...)
  3. Agent.register_action_channel(tool_id) for every WRITE organ
     + synthetic wait_and_monitor
  4. poll READ organs → WorldState.update
  5. GenericEncoder.encode(world_state, last_results) → context_events
     + optional external EmotionalImpulse[]
  6. agent.step(context_events, decision_only=True) → chosen tool_id
  7. SchemaBinder.bind(capability, world_state, rank_weights, memory_hint)
       → params | None
  8. if None or wait_and_monitor → no WRITE, no store
  9. ProposedAction(tool_id, params, risk, affect_snapshot)
 10. ApprovalGate.route → mcp_executor (единственный WRITE)
 11. GenericEncoder.encode_outcome(status, result)
       → tokens + EmotionalImpulse (via AffectiveSpace.outcome_impulse)
 12. hippocampus.store(path with ACTION=tool_id) + affective_space.step
 13. SleepScheduler as now (Process S + circadian)
```

Инварианты B2–B9 as-built **сохранить**. B1 заменить:

> **B1'** SchemaBinder / OrganRegistry / Encoder не вызывают `hippocampus.activate`, selector, `agent.step`. Read-only просмотр experiences для ranking **разрешён**, как сейчас read-only hippocampus в procurement adapter, но без доменных `_select_cheapest`.

### 5.3 Что удаляется

| Удалить / запретить | Замена |
|---|---|
| `MotorAdapter` и обязательный override `_build_params` | `SchemaBinder` |
| `ProcurementBodyMotorAdapter` | роль = YAML + seed + MCP servers |
| `MCPCapability.action_types` как необходимый индекс | `tool_id` = action; поле оставить deprecated, игнорировать в runtime |
| `role.motor_adapter: python:Class` | нет |
| `role.event_classifier: python:fn` как обязательный | generic encoder + optional YAML rules |
| Параллельный словарь `place_order_*` | seed/ACTION = `mcp__...__create_purchase_order` |

`ProposedAction`, `ApprovalGate`, `HardConstraintViolation`, `MCPToolRegistry` (переименовать смысл в OrganRegistry, файл можно оставить) — **остаются**.

---

## 6. Универсальные компоненты тела

Целевое размещение: пакет `src/mcp_body/` (платформа).  
`Demo/Virtual company/src/nowa_body/` в этой поставке можно либо (A) переехать в `src/mcp_body/` с re-export, либо (B) заменить файлы на месте и оставить пакет как тонкий host. **Предпочтение A**, чтобы ядро в `src/` было самодостаточно. Demo тогда: role YAML, MockMCP, GUI, bat-файлы.

Минимальный набор новых/переписанных модулей:

```
src/mcp_body/
  mcp_capability.py      # as-is + action_types deprecated
  risk_classifier.py     # heuristic, as-is
  organ_registry.py      # MCPToolRegistry + working discovery
  mcp_client.py          # transport protocol (stdio/sse/mock)
  world_state.py         # NEW
  schema_binder.py       # NEW — замена MotorAdapter
  field_lexicon.py       # NEW — универсальные имена полей
  generic_encoder.py     # замена BusinessEventEncoder+role classifier
  proposed_action.py     # ProposedAction dataclass (из motor_adapter.py)
  approval_gate.py
  hard_constraints.py
  feedback.py            # apply_feedback, status envelope
  runtime.py
  seeder.py              # ACTION = tool_id
```

### 6.1 MCP discovery (обязательная реализация)

`register_from_mcp_discovery` больше не stub.

Контракт клиента (минимальный):

```python
class MCPTransport(Protocol):
    def list_tools(self) -> list[MCPToolDescriptor]: ...
    def call_tool(self, name: str, arguments: dict) -> dict: ...
```

`MCPToolDescriptor`:

```
name: str
description: str
input_schema: dict   # JSON Schema object
output_schema: dict  # optional
```

Регистрация:

```
tool_id = f"mcp__{server_id}__{sanitize(name)}"
risk = yaml_override | classify_risk_heuristic(name, description)
requires_approval = True if risk in {HIGH_WRITE, IRREVERSIBLE} else yaml_or_default
```

YAML **может** перекрыть risk/approval/domain_tags; **не может** задать Python adapter.

Несколько серверов на агента — норма. Коллизии `tool_id` — ошибка конфигурации.

Живой 1С (позже) — ещё один `server_id` с `transport: stdio|sse` и command/url MCP-сервера. Каталог тулов 1С приходит из `tools/list`, не из захардкоженного procurement-списка. Если schema 1С использует русские имена полей — это `field_aliases` в YAML роли, не новый код платформы.

### 6.2 WorldState (проприоцепция)

```python
class WorldState:
    """Last sensory snapshot. No domain types."""
    results: dict[str, dict]          # tool_id -> last result envelope
    entities: dict[str, list[dict]]   # collection_name -> rows
    scalars: dict[str, float]         # dotted or leaf numeric paths
    updated_at: dict[str, float]
```

Обновление после каждого READ:

1. Сохранить envelope (`status` + payload).
2. Рекурсивно найти **списки объектов** (list[dict] с ключами id-like) → коллекция. Имя коллекции = ключ JSON (`suppliers`, `items`, `orders`) или `{tool_leaf}_{key}`.
3. Скаляры: все конечные number по dotted path `stock.SKU1.qty`.
4. Никакой закупки: нет класса Supplier.

### 6.3 Field lexicon (универсальный, не 1С)

`field_lexicon.py` — таблицы подстрок (lowercase) → роль признака:

| Роль | Примеры подстрок |
|---|---|
| `id` | `id`, `uuid`, `code`, `sku`, `number` (если не amount) |
| `cost` | `price`, `cost`, `amount`, `budget`, `total`, `fee` |
| `time` | `lead`, `eta`, `delay`, `duration`, `days`, `hours`, `latency` |
| `reliability` | `reliab`, `rating`, `score`, `trust`, `success_rate`, `otd` |
| `quantity` | `qty`, `quantity`, `stock`, `count`, `volume`, `coverage` |
| `status` | `status`, `state`, `available`, `active` |

Это **единственное** место «магии имён». Новый MCP с `unit_price` / `lead_time_days` работает без кода роли. Если сервер называет поля `foo_bar` — опциональный YAML alias:

```yaml
field_aliases:
  cost: ["cena", "stoimost"]
  id: ["ref_key"]
```

Aliases мержатся в lexicon **на роль**, не в Python.

### 6.4 SchemaBinder (замена MotorAdapter)

Вход: `MCPCapability`, `WorldState`, `rank_weights`, optional `hippocampus` read-only.  
Выход: `dict | None`.

Алгоритм:

1. Взять `input_schema` (JSON Schema). Если пустой — `{}` (валидный вызов без аргументов).
2. Для каждого required property:
   - **explicit binding** из YAML `param_bindings` (JSONPath в WorldState / last result);
   - иначе **exact name** в scalars / top-level last payloads;
   - иначе **lexicon**: property name классифицируется, ищется лучший скаляр той же роли;
   - иначе **entity pick**: если тип string/integer и есть коллекции, выбрать row (см. ranking), взять id-поле;
   - иначе **schema default**;
   - иначе bind fail → `None` (мышца недоступна).
3. Optional properties — заполнять если есть уверенный match, иначе опустить.
4. Enum в schema — выбрать значение ranking'ом (строки enum как кандидаты).
5. Никогда не throw наружу; ошибки → `None` (как MotorAdapter.resolve).

**Candidate ranking** для нескольких row/enum:

```
score(row) =
    - cost_aversion   * z(cost_field)
    - speed_seek      * z(time_field)     # меньше время лучше при speed_seek
    + reliability     * z(reliability_field)
    + novelty_seek    * unseen_bonus(id)
    + memory_bonus    * past_reward(tool_id, id)   # read-only hippocampus
    + assertiveness   * z(quantity)       # осторожно: только если quantity роль
```

`z` — z-score внутри текущего candidate set. Нет поля роли → 0.  
`unseen_bonus` — id не встречался в ACTION эпизодах этого tool_id.  
`memory_bonus` — средний reward эпизодов с этим id-токеном, clamp [-1,1].

**Запрещено** в binder: `if action_type == "urgent_reorder"`, `COVERAGE_DAYS = 30`, списки `_PRICE_KEYS` роли. Coverage/qty: если schema требует quantity, брать scalar quantity с min(schema.minimum, lexicon quantity); эвристика «30 дней покрытия» **только** как YAML `param_bindings` / `computed_params` декларативно, не как Python.

Декларативные вычисления (узкий DSL, без eval):

```yaml
computed_params:
  quantity:
    op: max
    args: [10, {path: "stock.*.qty", reduce: min}]
```

Если DSL не нужен в первой итерации — **не реализовывать**; quantity тогда только из schema+world. Не тащить procurement формулу в ядро.

### 6.5 GenericEncoder

Заменяет обязательный `classify_procurement_events`.

READ → tokens:

- `tool:<tool_id>`
- `server:<server_id>`
- `status:<status>`
- для каждого lexicon-скаляра: `field:<role>:<bucket>` где bucket ∈ {low, mid, high, rising, falling} относительно running stats WorldState
- `entity:<collection>:<id>` для выбранных/присутствующих id (cap N=32)

Optional YAML overlay `affective_mapping` / `token_rules` (как сейчас events) — **добавка**, не требование.

READ → impulses (слабые, intensity ≤ 0.4):

- `status` fail → `outcome_impulse("error")`
- резкий rising `cost` или falling `quantity` → stress+, valence−
- novelty новых ключей → curiosity+

Не дублировать роль-события `stock_critical_low` как единственный путь: они могут остаться YAML overlay.

### 6.6 Status envelope и `outcome_impulse`

Сохранить as-built envelope: executor всегда `dict` с `status`.

Нормализация:

| status (normalized) | valence | stress | trust | arousal | curiosity |
|---|---|---|---|---|---|
| accepted, success, ok | +0.4 | −0.1 | +0.2 | +0.1 | 0 |
| rejected, failed, error | −0.4 | +0.4 | −0.2 | +0.3 | 0 |
| timeout, unknown | −0.1 | +0.2 | −0.1 | +0.2 | +0.2 |

Остальные оси 0. Intensity = magnitude (default 1, clamp 0..1). Реализация — `AffectiveSpace.outcome_impulse`.

Feedback ACTION label: **всегда** `action:<tool_id>`. Поле `strategy` больше не нужно. Seed corpus мигрирует на tool_id.

### 6.7 Синтетический орган `wait_and_monitor`

Не MCP-тул. Всегда в каналах BG. Binder для него не вызывается. Нет store (B8).

### 6.8 Role YAML (целевой минимум)

```yaml
role_id: procurement
mcp_servers:
  - server_id: 1c_erp
    transport: mock | stdio | sse
    command: ...
    args: []
    url: ""
    enabled: true
    # optional per-tool overrides after discovery:
    tool_overrides:
      create_purchase_order:
        risk_level: medium_write
        requires_approval: true
        domain_tags: [procurement]
param_bindings: {}      # optional JSONPath
field_aliases: {}
affective_mapping: {}   # optional overlay
seed_corpus:
  - context_tokens: [field:quantity:low, domain:procurement]
    action: mcp__1c_erp__create_purchase_order
    consequence: stock_restored
    reward: 0.8
```

Нет `motor_adapter`. Нет обязательного `event_classifier`. Нет `action_types` на тулах.

`mcp_capabilities` статическим списком **разрешён как fallback** (тесты/mock без live list), но runtime обязан уметь discovery.

---

## 7. Связь разума с органами

### 7.1 Каналы BG = мышцы

При сборке агента роли:

```
for cap in registry.motor_capabilities():
    agent.register_action_channel(cap.tool_id)
agent.register_action_channel("wait_and_monitor")
```

Selector pressures строятся по токенам `action:<tool_id>` в гиппокампе. Поэтому seed **обязан** использовать те же id.

Не регистрировать READ тулы как мышцы (иначе агент «действует» опросом). Опрос — host/runtime.

### 7.2 Per-channel affective modulation (Agent)

Вместо одного `affect_modifier` на все действия:

```
bias = affective_space.decision_bias()
w = affective_space.rank_weights()
for tool_id, pressure in pressures:
    cap = registry.get(tool_id)
    if cap is None: continue
    if cap.risk_level in HIGH/IRREVERSIBLE:
        pressure *= (1.0 - 0.5 * w.caution)
    if cap.risk_level == READ_ONLY:
        pass  # not a channel
    pressure *= (1.0 + 0.2 * w.novelty_seek * novelty(tool_id))
```

Реализовать в `Agent._compute_affective_space_modifier` **или** рядом `_modulate_pressures_for_organs`. Не в SchemaBinder.

### 7.3 Когда params не собрались

Если выбран WRITE, но `bind` → None: трактовать как no-op этого тика (эквивалент wait). **Не** подставлять пустой dict, если schema.required непустой. Можно слегка internal impulse curiosity+ (не смог действовать — незавершённость), intensity ≤ 0.15.

### 7.4 Approval и аффект

`ProposedAction.affective_context = affective_space.snapshot()["axes"]` (как сейчас). Человек в UI видит A(t). A(t) **не** auto-approve.

---

## 8. Изменения ядра `src/` (обязательный чеклист)

1. `affective_space.py` — `outcome_impulse`, `rank_weights`.
2. `agent.py` — per-channel modulation; derive impulses без двойного счёта; BG aversive из stress+caution; hippocampus recall → memory impulses; project legacy after step.
3. `selector.py` — принять `affect_bias` dict; не ломать старые тесты (fallback scalar).
4. `basal_ganglia.py` — опциональные float gains от caller (уже есть aversive); документировать смысл.
5. `hippocampus.py` — store/activate контракт для EmotionalTrace (если нет — через Agent, не обязательно тащить import space в hippocampus: Agent glue допустим).
6. `value_layer.py` / `prediction_layer.py` — эмит импульсов наружу (return dict), Agent применяет.
7. `emotional_regulation.py` — убрать dual source of truth.
8. `semantic_emotions.py` — канонические оси.
9. `sleep.py` — background/wakefulness в step во время цикла.
10. `storage.py` — канон не перетирается projection.
11. `gui.py` — 8 осей + bias.
12. `intent_memory.py`, `self_model.py`, `affective_persistence.py` — читать snapshot A(t).
13. Тесты: расширить `tests/test_affective_space*.py`, integration agent, плюс новые `tests/test_mcp_body_schema_binder.py` (если пакет в src).

Не раздувать `Agent.step` доменной закупкой.

---

## 9. Миграция Demo procurement

1. Реализовать discovery на MockMCP (`list_tools` из каталога mock).
2. Переписать seed: `action: mcp__1c__create_purchase_order` (сохранить текущий tool_id стиль as-built `mcp__1c__...` если mock так называет — **единый** server_id).
3. Удалить использование `ProcurementBodyMotorAdapter` из runtime/configurator.
4. Configurator GUI: убрать обязательный класс motor; Discover tools = реальный list (mock).
5. Старые тесты `test_motor_adapter.py` / `test_procurement_motor_adapter.py`: заменить на SchemaBinder + ranking (дешёвый vs надёжный поставщик получается из A(t)+lexicon, не из action_type).
6. Регрессия: тот же MockMCP сценарий «критический остаток → create order» должен проходить без procurement Python.

Поведенческий эквивалент стратегий:

| Было (action_type) | Станет |
|---|---|
| place_order_cheap_supplier | тот же тул; высокий `cost_aversion` выбирает row с min price |
| place_order_reliable_supplier | высокий `reliability` вес |
| urgent_reorder | высокий `speed_seek` + stress → min lead time; qty из scalars |
| diversify_supplier | высокий `novelty_seek` → unseen id |
| wait_and_monitor | тот же синтетический канал |

Характер роли задаётся геномом/A(t)/seed, не четырьмя Python-ветками.

---

## 10. Тесты (обязательные)

Ядро:

- `outcome_impulse` маппинг status → оси в [-1,1]
- `rank_weights` монотонность: ↑stress ⇒ ↑caution; ↑curiosity ⇒ ↑novelty_seek
- regulation больше не расходится с `axes` после N шагов (один source)
- semantic emotions реагируют на канонический valence/stress
- save/load сохраняет новые методы не ломая старые ключи
- selector fallback scalar всё ещё работает

Тело:

- discovery: 4 mock tools → 3 sensory + 1 motor channel на агенте
- binder: schema `{supplier_id, sku, qty}` + world suppliers/stock → полный params
- binder: нет коллекции → None
- ranking: два поставщика price/reliability; cost_aversion высокий → дешёвый id
- нет MotorAdapter import в runtime happy path
- B5–B6 approval не сломаны
- seed с `action: mcp__...` даёт ненулевое давление на этот канал
- второй фиктивный MCP (email send) регистрируется тем же кодом без нового adapter-класса

Запрещено: тест, который требует `ProcurementBodyMotorAdapter`.

---

## 11. Порядок работ для агента-исполнителя

**Этап 0.** Зафиксировать as-built тесты, список падающих после удаления motor.

**Этап 1. Канон покрытия ядра** (`src/`): `outcome_impulse` + `rank_weights`; CER/semantic/selector/BG/sleep/persistence/GUI контракты §4. Не трогать Demo, пока ядро зелёное.

**Этап 2. WorldState + SchemaBinder + discovery** в `src/mcp_body` (или nowa_body). Unit tests без GUI.

**Этап 3.** Runtime без MotorAdapter; MockMCP; миграция procurement YAML/seed.

**Этап 4.** Configurator GUI + удаление мёртвого кода motor_adapter / role motor import.

**Этап 5.** Документация as-built: короткий addendum, что Phase1 MotorAdapter superseded этой спекой.

Каждый этап — отдельные коммиты по просьбе пользователя; без просьбы не коммитить.

---

## 12. Явный out of scope / запреты

Не «потом сделаем иначе», а **не делать вообще** в этой и следующих поставках тела/аффекта:

| Тема | Почему в спеке это вообще всплыло | Правило |
|---|---|---|
| Новые оси A(t) (`urgent`, `budget`, …) | Исполнитель может решить «срочность некуда положить» и добавить ось | Запрещено. Срочность = динамика уже существующих осей + ranking. Бюджет = WorldState/`cost`. |
| LLM / LLM-агент для `params` | Частый ложный путь: «schema сложная — пусть модель заполнит JSON» | Запрещено. Это ломает детерминизм, суверенитет и универсальность: каждый новый тул снова зависит от промпта. Binder покрывает любой MCP именно потому, что он не генерирует, а **связывает**. |
| Авто-approve HIGH/IRREVERSIBLE | Стресс/urgency могут соблазнить обойти gate | Запрещено. |
| Обучение наяву вне feedback-after-outcome | Как сейчас в теле | Не расширять. |
| Переписывание `nowa_sandbox` | Соседний контур | Не трогать; изоляция сохраняется. |

**Не out of scope — отложенный transport:** реальный MCP 1С. Его **не** реализуем в этой поставке (хватит Mock + протокола `MCPTransport`), но контракт обязан принять его без изменений ядра. Критерий: замена Mock → 1С MCP есть смена YAML `mcp_servers` (+ aliases при нужде), а не новый пакет `nowa_roles.procurement.one_c_adapter`.

---

## 13. Критерий готовности

Платформа считается покрытой и тело универсальным, если:

1. В `src/` нет модуля из §4 со статусом X.
2. Новый MCP сервер (включая будущий 1С) подключается YAML-ом transport + discovery, **ноль** новых Python-классов мышц и **ноль** новых осей A(t).
3. `grep MotorAdapter` в runtime path — только deprecated shim (если нужен на 1 релиз) или пусто.
4. Закупка на MockMCP работает через ranking A(t)+schema. Тот же binder обязан быть достаточен для тулов 1С, когда они появятся.
5. Канон A(t) — единственный write-target аффекта; `affect_state` совпадает с projection после каждого step.
6. В пайплайне bind/execute нет вызовов LLM.

---

## 14. Примечание исполнителю по именам файлов

На Windows пути `affective_space.py` / исторические имена могут совпадать регистром. Ориентир: модуль канона — тот, где объявлены `AXES`, `AffectiveSpace`, `decision_bias`. Пакет тела Demo сегодня: `nowa_body` (`mcp_capability.py`, `motor_adapter.py`, `tool_registry.py`, `runtime.py`). Не плодить параллельный `MotorAdapter` под новым именем — удалить концепт, не переименовать класс.

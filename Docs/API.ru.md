# Справочник API — NOWA Cognitive (Phase 5 EDPC + арбитраж решения + обдуманное планирование v2 + HIE-003/HIE-002 + присвоение кредита + Phase 6.2.1 + SAC + автономная среда исполнения + слой внешнего взаимодействия + CER + ACC + Packages A/B/C/D/E/F)

English version: [API.en.md](API.en.md)

**Статус (27 сентября 2026 г.).** Документ ядра. Актуальное научное изложение комплекса на русском и английском языках приведено в [SCIENTIFIC_DESCRIPTION.ru.md](SCIENTIFIC_DESCRIPTION.ru.md). Текст ниже сохраняет формулировки исходной редакции: это нормативный контракт модуля либо лабораторная запись.


Настоящий документ отражает текущую реализацию в:
- `src/agent.py`
- `src/autonomous_organism.py`
- `src/simulation_utility.py`
- `src/selector.py`
- `src/external_interaction_layer.py`
- `src/neuromodulators.py`
- `src/genome.py`
- `src/epigenome.py`
- `src/agent_factory.py`
- `src/fitness.py`
- `src/swarm.py`
- `src/reproduction.py`
- `src/mortality.py`
- `src/ecology.py`
- `src/population_observer.py`
- `src/value_layer.py`
- `src/conflict_arbitration.py`
- `src/decision_arbitrator.py`
- `src/hippocampal_imagine_engine.py`
- `src/sleep.py`
- `src/wakefulness.py`
- `src/storage.py`

Последняя проверка: 20 октября 2026 г. (двухуровневая пластичность, issue #13).

---

## Контракт с хостом и пластичность

Ядро не решает, когда спать и с какой скоростью идёт время.

| Обязанность | API |
|------------|-----|
| Средний интервал бодрствования между снами | `PlasticityConfig(expected_wake_interval_s=...)` при создании `Agent` |
| Продвинуть часы хоста на тике | `step(..., dt=...)`, `commit_executed_transition(..., dt=...)`, `advance_time(dt)` |
| Консолидировать стабильную память | `Agent.sleep(cycles=...)` (`learning_allowed()`) |
| Новые каналы действий | `register_action_channel` (внутри `initializing()`) |
| Посев после загрузки | `with initializing(): ...` |

`PlasticityConfig` в `src/labile_layer.py`. Guard: `NOWA_STRICT_LEARNING`, `WakingLearningError`, `stable_fingerprint`, `labile_snapshot`. Текст: [two-tier-plasticity.ru.md](../Docs/architecture/two-tier-plasticity.ru.md), [SLEEP.ru.md](SLEEP.ru.md).

### Host contract and plasticity

English table and parameter defaults: [API.en.md](API.en.md#host-contract-and-plasticity).

---

## Агент

Файл: `src/agent.py`

### `Agent.step(...) -> str`
```python
def step(
    self,
    context_events: list,
    consequence: Event = None,
    intensity: float = 1.0,
    reward: float = 0.0,
    novelty: float = 0.0,
    conflict: float = 0.0,
    affective_inputs: dict = None,
) -> str
```

Примечания о поведении:
1. Сначала обновляет динамику нейромодуляторов без награды (`update_from_signals(..., use_reward_for_dopamine=False)`).
2. Использует ACh текущего шага для онлайн-обновления ValueLayer.
3. Сохраняет метаданные воспроизведения в опыте гиппокампа:
   - `td_error_snapshot`
   - `replay_salience`
   - `replay_importance`
   - `acetylcholine_snapshot`
   - `encoding_strength`
4. Дофамин обновляется по дельте TD после обновления ценности.
5. Использует обязательный конвейер решения:
   - `ActionSelector.compute_pressures(...)`
   - `BasalGangliaGate.process(...)`
   - `ThalamicGate.select(...)`
6. `ActionSelector.compute_pressures(...)` возвращает только кортикальное и когнитивное давление.
   Аффективная и физиологическая модуляция применяется в BG (единственная точка модуляции).
7. Если все давления селектора равны нулю, а контекст непуст, агент вносит малое
   начальное давление контекста (`0.12`) для одного кандидата действия, выведенного из контекста.
8. `NO_ACTION` допустимо, когда сумма допущенных оценок равна нулю (случайного отката к действию нет).
9. ACC-подобный арбитраж применяется между давлением селектора и допуском BG:
   - вычисляет режим управления и дельты по метрикам конфликта и ошибки
   - изменяет только параметры порога, привычки и исследования BG
   - непосредственно действие не выбирает
10. Совместный сдвиг порога CER и ACC ограничен, чтобы исключить резонанс избыточного подавления.
11. Арбитраж решения применяется после ACC и до выбора BG:
   - `DecisionArbitrator.arbitrate(...)` вычисляет неопределённость и температуру политики
   - если режим равен `DELIBERATIVE`, планирование может перестроить вектор давлений
12. Контракт обдуманного планирования:
    - для каждого действия использует эпизодические воспоминания, отфильтрованные по сходству
    - вычисляет прогон по памяти и воображаемый прогон, затем смешивает их по правилу:
      `rollout_value = (1 - imagination_value_blend) * memory_rollout + imagination_value_blend * imagined_value`
    - в режиме HIE-003 (`imagination_enable_action_sequences=True`) значение `imagined_value` берётся из агрегации дерева корневого действия
    - в резервном режиме (`imagination_enable_action_sequences=False`) значение `imagined_value` берётся из структурированного воображения HIE-002 (`quantile(imagined_rollouts, 0.7)`)
    - сочетает оценку награды, ценность модели, ценность прогона, необязательное смещение EDPC и бонус VOI
    - глубина прогона адаптивна к неопределённости (ограничена пределами реализации)
    - бонус исследования равен `planning_exploration_gain * (1 - confidence)`
    - действие пропускается, если `support < 0.05` или `confidence < planning_min_confidence`
    - планирование изменяет только вектор давлений
13. Контракт гиппокампального воображения:
    - глобальный переключатель: `imagination_enabled`
    - путь дерева HIE-003: `Agent._generate_action_tree_imagination(...)` -> `HippocampalImagineEngine.generate_action_tree_imagination(...)`
    - структурированный резерв HIE-002: `Agent._generate_structured_imagination(...)` -> `HippocampalImagineEngine.generate_structured_imagination(...)`
    - оболочка совместимости сохранена: `Agent._generate_imagined_rollouts(...)`
    - воображаемые траектории раскрывают поля `root_action`, `cumulative_reward`, `terminal_state_value`, `value_estimate`, `novelty_score`, `confidence`, `depth`
    - жёсткие пределы HIE-003:
      - `imagination_action_branching <= 4`
      - `imagination_max_tree_nodes <= 128`
      - `imagination_depth <= 5`
    - жёсткие пределы HIE-002:
      - `imagination_samples <= 8`
      - `imagination_depth <= 5`
      - `imagination_branching <= 4`
      - `imagination_max_graph_nodes <= 96`
      - `imagination_max_graph_edges <= 192`
      - `imagination_max_nodes <= 96`
    - уверенность ограничена интервалом `[0.0, 1.0]`
    - ранняя остановка, когда дисконт прогона падает ниже `0.02`
    - член новизны вычисляется по невиданным воображаемым состояниям и примешивается к ценности траектории
14. Диагностика решения последнего шага хранится в
   `Agent._last_decision_arbitration_output` и доступна через `Agent.get_state()`.
15. Ведёт скользящие истории оценки для диагностики эволюционной приспособленности:
    - `affective_history` (снимки осей аффективного пространства)
    - `td_error_history` (текущая траектория ошибки TD)
    - `cortisol_history` (траектория стресса)
    с пределом по умолчанию `256` через `agent._fitness_history_limit`.

### `Agent.sleep(...) -> dict`
```python
def sleep(self, cycles: int = 3, sleep_duration_seconds: float = None) -> dict
```

Делегирует вызов `SleepManager.deep_sleep()` и возвращает агрегированную статистику сна.
Если автономная среда исполнения инициализирована, сон также снимает автономную энергетическую усталость.

### `Agent.get_state() -> dict`
Возвращает сводный снимок. Диагностика включает:
- `value_drift_ratio`
- `value_drift_warning`
- `neuromodulators` (включает поля ACh)
- `sleep_replay` (включает статистику воспроизведения по ACh и дисперсии)
- `decision_arbitration` (режим, неопределённость, надёжность, диагностика планирования)
- `credit_assignment` (`eligibility_trace_mean`, `credit_window_usage`, `replay_causality_mean`)
- `autonomous_runtime` (когда среда инициализирована)

### Методы автономной среды исполнения
```python
def init_autonomous_runtime(...) -> Optional[AutonomousOrganismAgent]
def autonomous_tick(dt: float = 1.0) -> dict
def get_autonomous_state() -> dict
def restore_autonomous_state(state: dict, force_recreate: bool = True) -> bool
```

Примечания о поведении:
1. `autonomous_tick()` продвигает автономный организм и бодрствование одним вызовом.
2. Снимок среды исполнения сохраняется и восстанавливается через хранилище.
3. Полезная нагрузка такта содержит диагностику физиологии и подробности обновления энергии.

### Методы внешнего взаимодействия
```python
def set_environment_interface(self, environment_interface) -> None

def observe_external_input(
    self,
    source: str,
    payload: Optional[Mapping[str, Any]] = None,
    uncertainty: float = 0.0,
    timestamp: Optional[float] = None,
) -> Observation

def get_external_observation_history(self, limit: Optional[int] = None)

def create_external_action(... ) -> ExternalAction

def poll_external_observation_non_blocking()
async def poll_external_observation_once()
async def execute_external_action(... ) -> dict

def resolve_external_feedback(current_step: Optional[int] = None) -> dict

def run_parallel_internal_simulations(simulation_requests: list) -> list

def get_external_interaction_state() -> dict
```

Примечания о поведении:
1. `execute_external_action(...)` поддерживает немедленную и отложенную обратную связь (`delay_feedback_steps`).
2. `resolve_external_feedback(...)` применяет все наступившие отложенные сигналы и возвращает обновления обучения.
3. Мост обучения агента отображает `predicted_effect.drives` селектора в `strategy_drive_coupling` и передаёт это значение во внешние хуки обучения.
4. Обновлённые веса стратегий отражаются в `selector.action_metadata[action]["strategy_weight"]`.

### Контракт выбора BG и таламуса в Agent
```python
def _select_action_via_basal_ganglia_pipeline(
    self,
    pressure_vector: dict,
    cer_modulation_factors: Optional[Mapping[str, Any]] = None,
) -> str
```

Примечания о поведении:
1. Строит модуляторы привычки и поканальные модуляторы из зарегистрированных `ActionChannel`.
2. Вычисляет `aversive_signal` из стресса аффективного ядра (`axes["stress"]`) с унаследованным откатом к `affect_state.threat`.
3. Читает факторы CER:
   - `exploration_bias`
   - `decision_threshold_shift`
   - `habit_gain_scale`
4. Читает управляющие факторы, скорректированные ACC и слитые с модуляцией CER:
   - ограниченный совместный `decision_threshold_shift`
   - `habit_gain_scale` с учётом ACC
   - `learning_rate_scale` с учётом ACC для онлайн-альфы ValueLayer
5. Вызывает `process(...)` у BG со слитыми факторами, затем `ThalamicGate.select(...)`.
6. `NO_ACTION` случайными действиями не подменяется.

---

## Непрерывная эмоциональная регуляция (CER)

Файл: `src/emotional_regulation.py`

### `EmotionalRegulationLayer.update(...) -> Dict[str, Any]`
```python
def update(
    self,
    reward_signal: float = 0.0,
    prediction_error: float = 0.0,
    novelty_score: float = 0.0,
    policy_entropy: float = 0.0,
    resolution_success: float = 0.0,
    time_delta: float = 1.0,
    timestamp: Optional[float] = None,
    **legacy_kwargs: Any,
) -> Dict[str, Any]
```

Примечания о поведении:
1. Поддерживает непрерывное состояние:
   - `valence` в интервале `[-1.0, 1.0]`
   - `arousal` в интервале `[0.0, 1.0]`
   - `uncertainty_tension` в интервале `[0.0, 1.0]`
2. Использует нелинейную ограниченную динамику с пороговыми эффектами и EMA по ошибке предсказания.
3. Налагает жёсткий предел скачка за шаг `<= 0.3` на каждую ядерную переменную.
4. Поддерживает `recovery_mode` и `saturation_guard` для предотвращения разгона.
5. Выдаёт `modulation_factors`:
   - `exploration_bias`
   - `learning_rate_scale`
   - `novelty_sensitivity_scale`
   - `decision_threshold_shift`
   - `habit_gain_scale`
6. Выдаёт ограниченные дельты `neuromodulator_guidance` в диапазоне `[-0.006, +0.006]`.

### `EmotionalRegulationLayer.apply_neuromodulator_guidance(...)`
```python
def apply_neuromodulator_guidance(
    self,
    neuromodulators: Any,
    guidance: Optional[Dict[str, float]] = None,
    gain: float = 1.0,
) -> Dict[str, float]
```

Примечания о поведении:
1. Применяет косвенное управление CER к состоянию нейромодуляторов.
2. Удерживает изменения в границах и ограничивает их предохранителями нейромодуляторов.

---

## Слой арбитража конфликта (ACC-подобный)

Файл: `src/conflict_arbitration.py`

### `ConflictArbitrationLayer.arbitrate(...) -> Dict[str, Any]`
```python
def arbitrate(
    self,
    *,
    go_signals: Optional[Iterable[Any]] = None,
    top2_gap: Optional[float] = None,
    policy_entropy: float = 0.0,
    decision_latency: float = 0.0,
    threshold_current: float = 0.0,
    arousal: float = 0.0,
    stress_level: float = 0.0,
    valence: float = 0.0,
    novelty_score: float = 0.0,
    pattern_completion_confidence: float = 0.0,
    prediction_error: float = 0.0,
    recent_failure_rate: Optional[float] = None,
    error_history_window: Optional[Iterable[Any]] = None,
    working_memory_load: float = 0.0,
    task_complexity: float = 0.0,
) -> Dict[str, Any]
```

Примечания о поведении:
1. Вычисляет:
   - `conflict_score`
   - `error_likelihood`
   - `control_demand` (включает член латентности)
2. Выбирает `control_mode` из набора:
   - `habitual`, `balanced`, `deliberative`, `inhibit`
3. Жёсткие ограничения:
   - пороги гистерезиса
   - рефрактерный период после обдуманного режима
   - штраф стоимости управления и принудительное понижение режима
   - максимальная подряд идущая серия `inhibit`
4. Возвращает только выходы управления:
   - `threshold_delta`
   - `control_gain_multiplier`
   - `wm_boost_flag`
   - `exploration_override`
   - `request_additional_evaluation`
5. Метрика конфликта намеренно независима от валентности и возбуждения, чтобы не дублировать CER.
6. Режим `inhibit` реализован давлением порога на пути BG, а обнуление моторного давления непосредственно не выполняется.

### `ConflictArbitrationLayer.register_outcome(reward_signal, prediction_error)`
Обновляет скользящие окна неудач и ошибок, используемые арбитражем.

### `ConflictArbitrationLayer.snapshot() -> Dict[str, Any]`
Возвращает диагностику исполнения и счётчики:
- распределение режимов
- использование стоимости управления
- счётчики рефрактерного периода и `inhibit`
- последние вычисленные метрики и выходы

---

## Слой арбитража решения (Spec 011)

Файл: `src/decision_arbitrator.py`

### `DecisionArbitrator.arbitrate(...) -> Dict[str, Any]`
```python
def arbitrate(
    self,
    *,
    pressure_vector: Optional[Mapping[str, float]] = None,
    action_metadata: Optional[Mapping[str, Mapping[str, Any]]] = None,
    error_likelihood: Optional[float] = None,
    surprise: Optional[float] = None,
    stress_level: Optional[float] = None,
    action_stability_mean: Optional[float] = None,
    causality_mean: Optional[float] = None,
) -> Dict[str, Any]
```

Примечания о поведении:
1. Вычисляет взвешенную неопределённость:
   - `global_uncertainty_raw = w_td * td_var + w_error * error + w_surprise * surprise`
   - `global_uncertainty` сглаживается EMA (`uncertainty_ema_beta`)
2. Применяет сдвиг порога с учётом стресса:
   - `effective_threshold = clamp(base_threshold - stress_gain * stress, min_threshold, 1.0)`
3. Применяет гистерезис режима:
   - предыдущий режим `DELIBERATIVE` снимается не сразу: для снятия неопределённость должна уйти ниже границы понижения
4. Вычисляет температуру политики:
   - `policy_temperature = clamp(base_temp + uncertainty_gain * global_uncertainty, temp_min, temp_max)`
5. Вычисляет надёжность политики, когда заданы устойчивость и причинность:
   - `policy_reliability = clamp(stability_mean * (1 - uncertainty) * causality_mean, 0, 1)`
   - низкая надёжность может принудительно включить режим `DELIBERATIVE`
6. Возвращает:
   - `decision_mode`
   - `global_uncertainty`, `global_uncertainty_raw`, `uncertainty_ema`
   - `policy_temperature`
   - `policy_reliability`
   - `effective_threshold`
   - `normalized_td_variance`
   - `hysteresis_margin`

### Интеграция в агента (`src/agent.py`)
1. Выход `DecisionArbitrator` сохраняется в `_last_decision_arbitration_output`.
2. Поля метаданных планирования включают:
   - `planning_bias_applied`
   - `planning_supported_actions`
   - `planning_support_mean`
   - `planning_rollout_depth`
   - `planning_rollout_samples`
   - `planning_rollout_used`
   - `planning_exploration_bonus_mean`
   - `planning_imagination_enabled`
   - `planning_imagination_samples`
   - `planning_imagination_depth`
   - `planning_imagined_rollouts_used`
   - `planning_imagined_value_mean`
   - `planning_imagined_value_max`
   - `planning_imagined_trajectory_count`
   - `planning_imagined_confidence_mean`
   - `planning_imagined_novelty_mean`
   - `planning_imagination_novelty_hits`
   - `planning_imagination_tree_nodes`
   - `planning_imagination_tree_edges`
   - `planning_imagination_action_count`
   - `planning_imagination_branching`
   - `planning_temperature_factor`
      (сохранено для совместимости; сейчас путь планирования даёт `1.0`)
3. Сводный снимок доступен через:
   - `Agent.get_state()["decision_arbitration"]`
   - `Agent.get_state()["credit_assignment"]`

---

## Среда исполнения автономного организма (Spec v1)

Файлы:
- `src/autonomous_organism.py`
- `src/agent.py`
- `src/gui.py`

### Основные классы
1. `AutonomousOrganismAgent`
2. `DriveSystem`
3. `EnergySystem`
4. `InternalSimulationLoop`
5. `SpeechGovernor`
6. `LifeLoopController`

### Таксономия побуждений (текущая)
Автономные побуждения:
- `curiosity`
- `social_drive`
- `goal_tension`
- `exploration`
- `energy_need`

Побуждениями не являются:
- `self_reflection` -> `agent_mode="REFLECTION"`
- `emotional_discharge` -> путь регуляции аффекта (`regulate_affect`)

### `AutonomousOrganismAgent.organism_step(dt) -> dict`
Основные поля результата:
- `timestamp`, `dt`, `dt_input`, `dt_clamped`
- `active_drive`, `active_drive_score`
- `internal_cycle_triggered`, `speech_event`, `speech_reason`, `speech_output`
- `agent_mode`, `mode_signals`
- `regulation`
- `physiology_mode`
- `cognitive_load`, `rest_time`, `load_components`
- `energy_level`, `energy_update`, `energy_snapshot`
- `drives`, `recall_impulse_share`

### `InternalSimulationLoop.run_cycle(...) -> dict`
```python
def run_cycle(
    self,
    active_drive: str,
    now: float,
    dt: float = 1.0,
    live_drives: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]
```

Поведение симуляции:
1. Работает только на гипотетических копиях.
2. Путь предложителя: `selector.choose(...)`.
3. Путь оценщика: `selector.evaluate(hypothetical_state)` (только полезность).
4. Общее вычисление полезности сосредоточено в `src/simulation_utility.py`.
5. Начальное значение гипотетического побуждения берётся из снимка `live_drives`, когда он доступен.
6. Путь предложения действия согласован с конвейером решения среды исполнения:
   `compute_pressures -> BG.process -> ThalamicGate.select`.

Контракт выхода симуляции (основные поля):
- `best_action`
- `confidence`
- `evaluated_variants`
- `decision`
- `fallback_used`

### Режимы физиологии
- `idle`
- `passive`
- `internal_processing`
- `speaking`
- `low_energy`

### Контракт журнала отказов
Записи об отказе имеют вид:
```python
{
    "timestamp": float,
    "failure_mode": str,
    "details": dict,
}
```

Типичные режимы:
- `drive_runaway_growth`
- `infinite_internal_cycle_loop`
- `speech_spam`
- `dt_anomaly`
- `internal_affect_apply_failed`
- `internal_decision_eval_failed`
- `decision_engine_choose_disallowed`
- `invariant_violation`
- `energy_deadlock`

---

## Заметки о трассе автономного режима в GUI

Файл: `src/gui.py`

### `NOWAGUI._autonomous_lifecycle_tick()`
Примечания о поведении:
1. Выполняет один автономный такт на каждом интервале жизненного цикла (по умолчанию `1s`).
2. Выводит речь в чат как `[AUTO] ...`, когда `speech_event=True`.
3. Выводит трассу внутренней мысли как `[AUTO] think: ...`, когда `internal_cycle_triggered=True`.

### `NOWAGUI._format_autonomous_internal_thought(tick) -> str`
Примечания о поведении:
1. Читает лучшее действие и уверенность из `tick` и `runtime.internal_loop.last_result`.
2. Показывает явный текст торможения для `NO_ACTION`:
   `NO_ACTION (BG gate inhibited)`.
3. Подавляет повторные строки мысли примерно на 4 секунды.

---

## Слой внешнего взаимодействия

Файл: `src/external_interaction_layer.py`

### Основные классы
1. `Observation`
2. `ExternalAction`
3. `Feedback`
4. `Hypothesis`
5. `DelayedFeedback`
6. `ExternalInteractionLayer`
7. `AsyncInteractionScheduler`

### `ExternalInteractionLayer.apply_learning_hooks(...) -> dict`
Основное поведение:
1. Обновления побуждений используют ограниченную нелинейную динамику с `drive_decay`, `drive_saturation`, `drive_competition`.
2. Обновления стратегий идут в пространстве логитов с `strategy_weight_decay` и нормализацией softmax (`strategy_temperature`).
3. Связь побуждения с политикой поддерживается через `strategy_drive_coupling` и `drive_policy_gain`.
4. Пересчёт гипотез поддерживает явную вероятность `P(E|¬H)` (`likelihood_not_h`) и необязательную базовую частоту свидетельства.

Возвращаемая диагностика включает:
- `drive_updates`, `strategy_updates`, `strategy_logits`
- `drive_levels`, `strategy_drive_signal`
- значения настройки (`drive_decay`, `strategy_temperature` и другие)

### Контракт связи политики селектора
Файл: `src/selector.py`

`ActionSelector.compute_pressures(...)` дополнительно читает необязательное поле:
- `action_metadata[action]["strategy_weight"]`

Этот вес центрируется относительно равномерной базовой линии и вносится в давление,
так что внешнее обучение стратегиям влияет на фактический выбор политики.

`action_metadata[action]` также хранит семантические поля SAC:
- `expected_effect_mean`
- `expected_effect_variance`
- `success_alpha`
- `success_beta`
- `risk_estimate`
- `semantic_confidence`
- поля синхронизации EDPC и SAC:
  - `confidence`, `stability`
  - `td_mean`, `td_variance`
  - `consolidated`, `consolidation_flag`
  - `conflict_flag`, `last_state_key`

### Интерактивный контракт GUI
Файл: `src/gui.py`

`Слой внешнего взаимодействия` поддерживает:
- ручной приём наблюдения (`источник`, `неопр.`, `данные JSON`)
- опрос среды (`Опрос среды`)
- исполнение действия (`действие`, `приор`, `задержка`, `прогноз`, `параметры JSON`)
- разрешение отложенной обратной связи и обновление статуса.

---

## Нейромодуляторы

Файл: `src/neuromodulators.py`

### `NeuromodulatorField`
Связанный слой взаимодействия для `DA/5HT/NE/ACh`.

Основное поведение:
1. Хранит уровни и базовые линии по каждой оси для:
   - `dopamine`
   - `serotonin`
   - `norepinephrine`
   - `acetylcholine`
2. Использует матрицу взаимодействия `W` из `spec_neuromodulator_interaction_layer.md`.
3. Применяет связанное обновление, центрированное на базовой линии:
   - `dM/dt = base_signal + W * (M - baseline) - decay * (M - baseline)`
4. Предоставляет:
   - `update(signals: Optional[Dict[str, float]] = None, dt: Optional[float] = None) -> Dict[str, float]`
   - `snapshot()`, `reset()`
   - `to_dict()` / `from_dict()`

### `NeuromodulatorState`
Конструктор:
```python
NeuromodulatorState(
    dopamine: float = None,
    norepinephrine: float = None,
    serotonin: float = None,
    cortisol: float = None,
    acetylcholine: float = None,
)
```

Основные поля:
- скалярные нейромодуляторы: `dopamine`, `serotonin`, `norepinephrine`, `cortisol`, `acetylcholine`
- объект связанного взаимодействия: `interaction_field` (`NeuromodulatorField`)
- следы конфликта ACC:
  - `acc_combined_conflict_trace`
  - `acc_cognitive_conflict_trace`
  - `acc_affective_conflict_trace`

Основные параметры ACh:
- `acetylcholine` в интервале `[0.0, 1.0]`
- `ach_baseline`
- `ach_decay_rate`
- `ach_novelty_gain`
- `ach_repetition_penalty`
- `ach_novelty_filter`
- `ach_novelty_trace`
- `ach_alpha_gain`
- `ach_replay_gain`

### `update_acetylcholine(...)`
```python
def update_acetylcholine(self, novelty: float = 0.0, stable_repetition: bool = False)
```

Правила:
1. Сглаживает новизну фильтром `ach_novelty_filter` в след `ach_novelty_trace`.
2. Повышает ACh только при высокой эффективной новизне.
3. Понижает ACh при устойчивом повторении.
4. Затухает ACh к базовой линии и ограничивает значение интервалом `[0.0, 1.0]`.

### `update_from_signals(...)`
```python
def update_from_signals(
    self,
    reward: float = 0.0,
    novelty: float = 0.0,
    conflict: float = 0.0,
    stable_repetition: bool = False,
    use_reward_for_dopamine: bool = True,
    cognitive_conflict: Optional[float] = None,
    affective_conflict: Optional[float] = None,
    dt: float = 1.0,
)
```

Поведение с учётом ACC:
1. Разрешает скалярный и расщеплённый каналы конфликта с симметричной семантикой `None`:
   - если оба равны `None`, оба используют `conflict`
   - если один равен `None`, зеркалируется предоставленный канал
2. Вычисляет целевые конфликты ACC (`combined/cognitive/affective`) по снимку состояния (`NE/CORT/5HT`) через `_compute_effective_conflict_from_state(...)`.
3. Применяет низкочастотное временное сглаживание с `alpha = 1 - exp(-dt / tau)` ко всем трём следам.
4. Использует сглаженные каналы для обновления нейромодуляторов:
   - `NE` получает конфликт с когнитивной модуляцией и гомеостатическое затухание к базовой линии.
   - `CORT` получает конфликт с аффективной модуляцией и гомеостатическое затухание к базовой линии.
5. Усиление награды `5HT` пропускается сглаженным совместным следом конфликта (`reward > 0 and effective_conflict_combined <= 0.0`).
6. Вычисляет дельту ACh по новизне и повторению плюс затухание к базовой линии.
7. Применяет быструю связанную динамику (`DA/5HT/NE/ACh`) через `interaction_field.update(..., dt=dt)` на той же шкале шага.
8. Ограничивает все значения и обновляет метку времени.
9. `cortisol` намеренно обновляется вне `NeuromodulatorField` (медленная ось стресса по замыслу).

### Снимок и сохранение
- `snapshot()` и `to_dict()` включают:
  - все поля, связанные с ACh
  - следы ACC (`acc_combined/cognitive/affective_conflict_trace`)
  - `interaction_field`
- `from_dict()` восстанавливает состояние ACh, ACC и слоя взаимодействия.
- Обратная совместимость:
  - полезная нагрузка без `interaction_field` по-прежнему поддерживается.
  - унаследованный `acc_conflict_trace` принимается как откат, когда расщеплённые следы отсутствуют.

---

## Вектор генома (Package A)

Файл: `src/genome.py`

### Основные объекты
1. `GeneDescriptor`
2. `GENE_REGISTRY` (детерминированный упорядоченный каталог)
3. `GenomeVector`

### API создания `GenomeVector`
```python
GenomeVector.default() -> GenomeVector
GenomeVector.random(rng: random.Random | None = None) -> GenomeVector
GenomeVector.from_dict(data: dict) -> GenomeVector
GenomeVector.from_array(array: List[float], generation: int = 0) -> GenomeVector
```

Примечания о поведении:
1. `from_dict(...)` игнорирует неизвестные ключи генов.
2. Отсутствующие гены заполняются значениями по умолчанию из дескриптора.
3. Значения вне диапазона ограничиваются границами дескриптора.
4. Порядок генов детерминирован (порядок `GENE_REGISTRY`).

### API эволюции
```python
GenomeVector.mutate(rate=0.05, sigma_scale=1.0, rng=None) -> GenomeVector
GenomeVector.crossover(other, alpha=0.5, mode="arithmetic", rng=None) -> tuple[GenomeVector, GenomeVector]
```

Примечания о поведении:
1. `mutate(...)` ограничивает `rate` интервалом `[0.0, 1.0]`.
2. `mutate(...)` ограничивает `sigma_scale` интервалом `[0.1, 5.0]`.
3. Режимы `crossover(...)`:
   - `arithmetic`
   - `uniform`
   - `sbx` (`eta=2`)
4. Неизвестный режим скрещивания вызывает `ValueError`.
5. Поколение потомка равно `max(parent_a.generation, parent_b.generation) + 1`.
6. Линия потомка составляется как `f"{a.lineage_id}x{b.lineage_id}"[:64]`.

### Диагностика и преобразование
```python
GenomeVector.distance(other) -> float
GenomeVector.similarity(other) -> float
GenomeVector.validate() -> List[str]
GenomeVector.summary() -> dict
GenomeVector.to_dict() -> dict
GenomeVector.to_array() -> List[float]
GenomeVector.to_agent_params() -> dict
```

Примечания о поведении:
1. `distance(...)` есть нормированное евклидово расстояние в интервале `[0.0, 1.0]`.
2. `summary()` сообщает статистику по группам (`NM/AF/WK/DR/LR/IM`):
   - `mean`
   - `std`
   - `deviation_from_default`
3. `to_agent_params()` разворачивает значения генома для:
   - `affective_space`
   - `wakefulness`
   - `neuromodulators`
   - `autonomous`
   - `value_layer`
   - `hippocampus`
   - `sleep`
   - `imagination`
4. `to_agent_params()["autonomous"]` включает `perception_radius_factor` из
   `dr_perception_radius_factor` для масштабирования восприятия в рое.

### Покрытие
1. `tests/test_genome_vector.py` проверяет TC-01..TC-14 из `Docs/SPEC_A_GenomeVector.md`.
2. Дополнительные тесты покрывают детерминизм SBX и усечение линии.

---

## Снимок эпигенома (Package B)

Файл: `src/epigenome.py`

### Основные объекты
1. `InheritedPattern`
2. `InheritedAction`
3. `InheritedValue`
4. `EpigenomeSnapshot`

### Константы
1. `EPIGENOME_VERSION = "1.0"`
2. `MAX_PATTERNS = 32`
3. `MAX_ACTIONS = 16`
4. `MAX_VALUES = 24`

### API создания `EpigenomeSnapshot`
```python
EpigenomeSnapshot.extract(
    cortex_patterns: List[dict],
    action_metadata: Dict[str, dict],
    value_profiles: Dict[str, dict],
    source_generation: int = 0,
    source_lineage_id: str = "",
    max_patterns: int = 32,
    max_actions: int = 16,
    max_values: int = 24,
    min_reinforcement: int = 2,
    min_stability: float = 0.5,
    min_confirmation: float = 1.0,
) -> EpigenomeSnapshot
EpigenomeSnapshot.from_dict(data: dict) -> EpigenomeSnapshot
EpigenomeSnapshot.empty() -> EpigenomeSnapshot
```

Примечания о поведении:
1. `extract(...)` принимает только полевые нагрузки dict и list и пропускает повреждённые строки, не возбуждая исключение.
2. `extract(...)` ограничивает параметры `max_*` интервалом `[1, 256]`.
3. Политика отбора:
   - паттерны: верхние N по `reinforcement_count` (по убыванию)
   - действия: верхние N по `stability_score` (по убыванию), только при `consolidated=True`
   - ценности: верхние N по `confirmation_count` (по убыванию)
4. `source_generation` нормализуется к неотрицательному значению.
5. `extraction_timestamp` назначается при извлечении.

### API переноса
```python
EpigenomeSnapshot.inject(
    target_cortex_patterns: list,
    target_action_metadata: dict,
    target_value_profiles: dict,
    noise_level: float = 0.1,
    rng: random.Random | None = None,
) -> dict
```

Примечания о поведении:
1. `inject(...)` изменяет цели на месте.
2. `noise_level` ограничивается интервалом `[0.0, 1.0]`.
3. Существующие ключи действий и ценностей сохраняются (перезаписи нет).
4. Записи паттернов заменяются только если унаследованная `strength` выше.
5. Возвращает счётчики переноса:
   - `patterns_injected`, `patterns_skipped`
   - `actions_injected`, `actions_skipped`
   - `values_injected`, `values_skipped`
   - `noise_level`

### API смешения
```python
EpigenomeSnapshot.blend(
    other: EpigenomeSnapshot,
    alpha: float = 0.5,
    rng: random.Random | None = None,
) -> EpigenomeSnapshot
```

Примечания о поведении:
1. `alpha` ограничивается интервалом `[0.0, 1.0]`.
2. Дубликаты паттернов берут большую `strength`.
3. Дубликаты действий берут больший `stability_score`.
4. Дубликаты ценностей сливаются:
   - `value = alpha * self + (1 - alpha) * other`
   - `confidence = min(self, other)`
5. Размеры выхода ограничены `MAX_PATTERNS`, `MAX_ACTIONS`, `MAX_VALUES`.
6. Линия составляется как `f"{left}+{right}"[:64]`.

### API диагностики и сериализации
```python
EpigenomeSnapshot.to_dict() -> dict
EpigenomeSnapshot.is_empty() -> bool
EpigenomeSnapshot.size() -> dict
EpigenomeSnapshot.validate() -> List[str]
EpigenomeSnapshot.summary() -> dict
```

Примечания о поведении:
1. `to_dict()` сортирует строки:
   - паттерны по силе
   - действия по устойчивости
   - ценности по числу подтверждений
2. `from_dict(...)` пропускает повреждённые строки с предупреждениями.
3. `validate()` проверяет диапазоны, конечность значений, дубликаты и отрицательные счётчики.
4. Внутренности снимка остаются неизменяемыми (`frozen=True` и хранение в кортежах).

### Покрытие
1. `tests/test_epigenome_snapshot.py` проверяет TC-01..TC-16 из `Docs/SPEC_B_EpigenomeSnapshot.md`.

---

## Фабрика агентов (Package C)

Файл: `src/agent_factory.py`

### Основные объекты
1. `AgentConfig`
2. `AgentFactory`

### `AgentConfig`
```python
AgentConfig(
    actions: List[str],
    hippocampus_capacity: int = 512,
    cortex_capacity: int = 256,
    sleep_cycles_default: int = 3,
    intent_memory_enabled: bool = True,
    environment_id: str = "",
)
```

### API создания
```python
AgentFactory.spawn(
    genome: GenomeVector,
    epigenome: EpigenomeSnapshot | None = None,
    epigenome_noise: float = 0.1,
    rng: random.Random | None = None,
    agent_id: str = "",
) -> Agent

AgentFactory.spawn_random(
    rng: random.Random | None = None,
    agent_id: str = "",
) -> Agent

AgentFactory.spawn_default(agent_id: str = "") -> Agent

AgentFactory.spawn_child(
    parent_a: Agent,
    parent_b: Agent,
    mutation_rate: float = 0.05,
    sigma_scale: float = 1.0,
    crossover_alpha: float = 0.5,
    crossover_mode: str = "arithmetic",
    epigenome_noise: float = 0.1,
    blend_epigenomes: bool = True,
    rng: random.Random | None = None,
    agent_id: str = "",
) -> Agent
```

Примечания о поведении:
1. `spawn(...)` всегда возвращает рабочего `Agent` и присоединяет:
   - `agent.genome`
   - `agent.epigenome`
   - `agent.agent_id`
   - `agent.lineage_id`
   - `agent.factory_config`
2. `epigenome_noise` ограничивается интервалом `[0.0, 1.0]`.
3. Недействительная полезная нагрузка эпигенома не прерывает порождение.
4. `spawn_child(...)` создаёт одного потомка (второй потомок скрещивания отбрасывается).
5. `spawn_child(...)` ограничивает параметры мутации и скрещивания безопасными диапазонами.

### API извлечения
```python
AgentFactory.extract_genome(agent: Agent) -> GenomeVector

AgentFactory.extract_epigenome(
    agent: Agent,
    max_patterns: int = 32,
    max_actions: int = 16,
    max_values: int = 24,
    min_reinforcement: int = 2,
    min_stability: float = 0.5,
    min_confirmation: float = 1.0,
) -> EpigenomeSnapshot
```

Примечания о поведении:
1. `extract_genome(...)` возвращает `agent.genome`, когда он есть; иначе восстанавливает геном из живых модулей.
2. `extract_epigenome(...)` использует публичное состояние исполнения (`cortex`, `selector.action_metadata`, `value_layer.expectation_memory`) и делегирует `EpigenomeSnapshot.extract(...)`.
3. Пути восстановления и инъекции отказоустойчивы и выдают предупреждения вместо исключений.

### Контракт отображения матрицы нейромодуляторов

Для генов нейромодуляторов индексы матрицы толкуются как `W[target][source]`:
1. `nm_da_ne_weight` -> `W[NE][DA]`
2. `nm_ne_da_weight` -> `W[DA][NE]`
3. `nm_da_ach_weight` -> `W[ACh][DA]`
4. `nm_ach_da_weight` -> `W[DA][ACh]`

Одно и то же отображение согласованно используется в обоих местах:
1. `_apply_neuromodulator_overrides(...)`
2. `_reconstruct_genome(...)`

### Покрытие
1. `tests/test_agent_factory.py` проверяет TC-01..TC-16 из `Docs/SPEC_C_AgentFactory.md`.
2. Дополнительное покрытие включает согласованность кругового прохода матрицы нейромодуляторов.

---

## Оценщик приспособленности (Package D)

Файл: `src/fitness.py`

### Основные объекты
1. `FitnessVector` (`frozen=True`)
2. `ParetoRank` (`frozen=True`)
3. `FitnessEvaluator`

### Константы
1. `FITNESS_VERSION = "1.0"`
2. `CRITERIA_ORDER`:
   - `longevity`
   - `affective_range`
   - `prediction_skill`
   - `stress_resilience`
   - `behavioral_diversity`
   - `learning_efficiency`
   - `memory_quality`
3. `DEFAULT_WEIGHTS`
4. `AFFECTIVE_RANGE_NORM = 0.5`
5. `LEARNING_EFFICIENCY_NORM = 3.0`
6. `MEMORY_QUALITY_SAMPLE_LIMIT = 128`

### Основной API
```python
FitnessEvaluator(weights: Dict[str, float] | None = None)

FitnessEvaluator.evaluate(agent: Any) -> FitnessVector
FitnessEvaluator.evaluate_population(agents: List[Any]) -> List[FitnessVector]
FitnessEvaluator.pareto_rank(fitness_vectors: List[FitnessVector]) -> List[ParetoRank]
FitnessEvaluator.scalar_score(fitness: FitnessVector) -> float
FitnessEvaluator.dominates(a: FitnessVector, b: FitnessVector) -> bool
FitnessEvaluator.criteria_names() -> List[str]
FitnessEvaluator.fitness_to_dict(fitness: FitnessVector) -> dict
FitnessEvaluator.fitness_from_dict(data: dict) -> FitnessVector
```

Примечания о поведении:
1. Оценка только для чтения и безопасна к исключениям: повреждённые данные агента сводятся к значениям критериев `0.0`.
2. Все значения критериев ограничены интервалом `[0.0, 1.0]`.
3. Поведение при отсутствии историй:
   - предсказание: используется `value_layer.snapshot()["last_td_error"]`, когда `td_error_history` отсутствует или пуста
   - стресс: используется `neuromodulators.cortisol`, когда `cortisol_history` отсутствует или пуста
4. `pareto_rank(...)` детерминирован и возвращает результаты, отсортированные по `(rank ASC, crowding_distance DESC)`.
5. Граничные векторы каждого фронта получают `crowding_distance = float("inf")`.
6. `scalar_score(...)` использует нормированные веса и возвращает значение в интервале `[0.0, 1.0]`.

### Поддержка на стороне агента во время исполнения
`Agent.step(...)` ведёт скользящие истории, требуемые Package D:
1. `agent.affective_history: List[dict]`
2. `agent.td_error_history: List[float]`
3. `agent.cortisol_history: List[float]`
4. скользящий предел через `agent._fitness_history_limit` (по умолчанию `256`)

### Покрытие
1. `tests/test_fitness.py` проверяет TC-01..TC-18 из `Docs/SPEC_D_FitnessEvaluator.md`.
2. `tests/test_fitness_agent_integration.py` проверяет контракт накопления истории исполнения в `Agent.step(...)`.

---

## Среда роя (Package E)

Файл: `src/swarm.py`

### Основные объекты
1. `Position3D`
2. `SpaceBounds`
3. `SocialSignal`
4. `AgentSlot`
5. `SwarmState`
6. `SwarmConfig`
7. `SwarmEnvironment`

### Константы
1. `SWARM_VERSION = "2.2"`
2. `MAX_POPULATION_SIZE = 256`
3. `MIN_AGENT_DISTANCE = 0.1`
4. `SIGNAL_MIN_STRENGTH = 0.01`
5. `MAX_SOCIAL_SIGNAL_GAIN = 0.5`
6. `SLEEP_HYSTERESIS_FACTOR = 0.7`
7. `SLEEPING_SIGNAL_FACTOR = 0.3`
8. `WAKE_SIGNAL_THRESHOLD = 0.6`

### Основной API
```python
SwarmEnvironment(
    config: SwarmConfig,
    fitness_evaluator: FitnessEvaluator,
    rng: random.Random | None = None,
    factory: Any | None = None,
)

SwarmEnvironment.add_agent(agent: Any, position: Position3D | None = None) -> Position3D
SwarmEnvironment.remove_agent(agent_id: str) -> Any | None
SwarmEnvironment.move_agent(agent_id: str, new_position: Position3D) -> bool
SwarmEnvironment.get_agent(agent_id: str) -> Any | None
SwarmEnvironment.get_position(agent_id: str) -> Position3D | None
SwarmEnvironment.get_all_agents() -> List[Any]
SwarmEnvironment.replace_population(agents: List[Any]) -> None

SwarmEnvironment.get_agents_in_radius(
    agent_id: str,
    radius: float | None = None,
    include_sleeping: bool = True,
) -> List[Tuple[Any, float]]
SwarmEnvironment.collect_signals_for_agent(agent_id: str) -> List[SocialSignal]
SwarmEnvironment.apply_social_signal(agent: Any, signal: SocialSignal, gain: float) -> None

SwarmEnvironment.tick(dt: float = 1.0, context_override: Dict[str, List[str]] | None = None) -> SwarmState
SwarmEnvironment.run_generation(steps: int | None = None, dt: float = 1.0) -> List[SwarmState]

SwarmEnvironment.get_diversity() -> float
SwarmEnvironment.get_swarm_state() -> SwarmState
SwarmEnvironment.evaluate_all() -> List[FitnessVector]
SwarmEnvironment.get_sleeping_agents() -> List[str]
SwarmEnvironment.get_active_agents() -> List[str]
SwarmEnvironment.get_nearest_agents(position: Position3D, k: int = 5, include_sleeping: bool = True) -> List[Tuple[Any, float]]
SwarmEnvironment.get_spatial_density(position: Position3D, radius: float) -> float
```

### Примечания о поведении
1. Пространство непрерывно и трёхмерно; двумерный режим представлен как `SpaceBounds(z_min == z_max)`.
2. Размещение обеспечивает исключение с минимальным попарным расстоянием `MIN_AGENT_DISTANCE`.
3. Радиус восприятия в `add_agent(...)` масштабируется геномом:
   - `base_perception_radius * genome.genes["dr_perception_radius_factor"]`
4. Спящие агенты остаются видимыми соседям и по-прежнему получают сигналы.
5. Сигналы от спящих источников ослабляются множителем `SLEEPING_SIGNAL_FACTOR`.
6. Пробуждение по сигналу использует накопленный член стресса:
   - `sum(signal.stress * signal.signal_strength) >= wake_signal_threshold`
7. `replace_population(...)` не сбрасывает `global_step`.
8. Цикл такта детерминирован по отсортированному `agent_id`; отказ одного агента не останавливает остальных.
9. `context_events_fn` необязателен; при его отсутствии среда даёт контекстные события по умолчанию:
   - состояние активности (`agent_active` / `agent_sleeping`)
   - корзина бодрствования (`wakefulness_high` / `wakefulness_mid` / `wakefulness_low`)
   - социальные маркеры (`social_signal_present`, `social_sleeping_neighbor`, `social_stress_high`)
10. Расширение эмерджентного жизненного цикла:
   - среда включает ресурсный слой `ecology`
   - такт включает обновления витальности, проверки смертности и децентрализованное спаривание для размножения
   - `SwarmState` включает метрики ресурсов, рождений и смертей

### Покрытие
1. `tests/test_swarm_environment.py` проверяет TC-01..TC-18 из
   `Docs/SPEC_E_SwarmEnvironment_v2.1.md`.
2. Дополнительные тесты проверяют события отката к контексту по умолчанию, когда пользовательская
   `context_events_fn` не задана.
3. `tests/test_emergent_evolution_v2.py` проверяет интеграционные сценарии путей ресурсов, смертности и размножения.

---

## Эмерджентная эволюция (Package F)

Файлы:
1. `src/reproduction.py`
2. `src/mortality.py`
3. `src/ecology.py`
4. `src/population_observer.py`

Основные API:
```python
ReproductiveSystem.update(
    energy: float,
    valence: float,
    cortisol: float,
    lived_steps: int,
    resource_share: float,
) -> None
ReproductiveSystem.is_ready() -> bool
ReproductiveSystem.register_reproduction(current_step: int) -> None
compute_compatibility(agent_a_snapshot: dict, agent_b_snapshot: dict) -> float

MortalitySystem.update(
    energy: float,
    wakefulness: float,
    lived_steps: int,
    cortisol_mean: float,
) -> bool
MortalitySystem.is_dead() -> bool
MortalitySystem.get_age_fraction(lived_steps: int) -> float

EcologyLayer.compute_resource_share(agent_count: int) -> float
EcologyLayer.consume(agent_count: int) -> float

PopulationObserver.observe() -> PopulationSnapshot
PopulationObserver.save(path: str) -> None
PopulationObserver.load(path: str, environment: SwarmEnvironment) -> PopulationObserver
```

---

## Слой ценности

Файл: `src/value_layer.py`

### `ValueLayer.update(...) -> dict`
```python
def update(
    self,
    state_snapshot: Mapping[str, Any],
    reward: float,
    next_state_snapshot: Mapping[str, Any],
    gamma: float = 0.95,
    alpha: Optional[float] = None,
    timestamp: Optional[float] = None,
    stability_index: Optional[float] = None,
    mode: str = "online",
    acetylcholine: Optional[float] = None,
    acetylcholine_baseline: Optional[float] = None,
    acc_learning_boost: Optional[float] = None,
    cer_stress_level: Optional[float] = None,
    exploration_baseline: Optional[float] = None,
    reward_scale: Optional[float] = None,
) -> Dict[str, Any]
```

Поведение TD и награды:
1. `reward_raw` берётся из среды как есть (внутреннего ограничения до `[-1, 1]` нет).
2. Эффективная награда равна `reward_scaled = reward_raw * reward_scale_v`.
3. Сырая TD сохраняется в диагностике: `delta = reward_scaled + gamma * V(s_next) - V(s)`.
4. Онлайн-фазическая TD обрезается величиной `td_clip_online`; режим сна использует фиксированное обрезание `1.0`.
5. Возвращаемая диагностика включает `delta`, `delta_modulated`, `delta_clipped`, `td_was_clipped`, `td_clip_value`, `td_clip_frequency`, `td_clip_frequency_ema`.
6. Необязательное адаптивное обрезание (`adaptive_td_clip_enabled`) подстраивает `td_clip_online` к `td_clip_target_rate`.
7. Тонический дофамин обновляется медленным фильтром (`tonic_slow_rate`, по умолчанию `0.01`) от бегущего `mean_phasic`, а не мгновенными скачками.

Поведение стресса и исследования:
1. Стресс CER снижает эффективную альфу (`stress_scale = max(0.2, 1 - 0.5 * stress)`).
2. Стресс CER усиливает отрицательную фазическую TD через `stress_dip_gain` (модуляция только провала).
3. Знак TD управляет связью с исследованием при ограниченной амплитуде (`<= 20%` базовой линии).
4. Когда базовое исследование близко к нулю, `exploration_unfreeze_floor` удерживает связь активной.
5. В `Agent.step()` дополнительные ограждения ограничивают сдвиг исследования по TD за шаг и задают пол режима inhibit (`0.05..0.20`).

Диагностика фазического и тонического компонентов:
1. `update(...)` возвращает `phasic_burst`, `phasic_delta`, `mean_phasic`, `tonic_level`.
2. `snapshot()` раскрывает `td_tonic_slow_rate`, `td_phasic_mean`, `td_tonic_target_base`.
3. `to_dict()` и `from_dict()` сохраняют и восстанавливают те же поля тонической динамики.

Поведение ACh:
1. Применяется только при `mode="online"`.
2. Использует сигнал относительно базовой линии: `ach_effective = max(0.0, ach - ach_baseline)`.
3. Масштабирование онлайн-альфы: `alpha = alpha * (1 + ach_alpha_gain * ach_effective)`.
4. Мягкий предел задаётся `alpha_online_soft_cap`.
5. При `mode="sleep"` ACh альфу не масштабирует.

Поведение EDPC (Phase 5):
1. Память ожидания по каждому закодированному состоянию ведётся в `ValueLayer.expectation_memory`:
   - `expected_reward_mean`
   - `expected_reward_var`
   - `confirmation_count`
   - `confidence_score`
   - `stability_score`
   - `error_likelihood`
   - `prediction_shock` (оценка) и `prediction_shock_flag`
   - `predicted_value`
   - `last_updated_step`
2. `update(...)` вычисляет диагностику EDPC и возвращает:
   - `expected_reward_mean`, `expected_reward_var`
   - `confirmation_count`, `confidence_score`, `stability_score`
   - `surprise`
   - `prediction_shock` (bool) и `prediction_shock_score` (float)
   - `replay_priority`
   - `consolidation_weight`
   - `shock_replay_boost`
3. Онлайн-эффективная альфа включает избирательное демпфирование и усиление при шоке:
   - демпфирование: `1 - confidence * stability * stability_damping`
   - шок: временный множитель `(1 + shock_plasticity_boost)`, когда шок обнаружен
4. `snapshot()` включает метрики EDPC:
   - `confidence_distribution`, `stability_distribution`
   - `shock_count_total`, `shock_frequency`, `shock_frequency_ema`
   - `effective_alpha_trajectory`
5. Извлечение ожидания по сходству для невиданных состояний:
   - векторизованное детерминированное кодирование (`state_vector` / `state_features`)
   - текстовые поля используют детерминированное семантическое хеширование (случайных текстовых векторов нет):
     - токенизация нечувствительна к регистру и основана на разбиении (`eat_food` -> `["eat", "food"]`)
     - каждый токен отображается в устойчивый единичный вектор хешированием на основе SHA-256
     - вектор фразы есть нормированное среднее векторов токенов
   - корзинный просмотр кандидатов по косинусу (`similarity_bucket_bits`, `similarity_bucket_radius`)
   - ограниченный пул кандидатов (`similarity_index_max_candidates`, `similarity_max_scan`)
   - взвешенный перенос уверенности и устойчивости через квантильный якорь (`similarity_transfer_quantile`)
6. Диагностика сходства во время исполнения раскрывается в `snapshot()`:
   - `last_similar_state_count`
   - `last_similarity_scan_count`
   - поля конфигурации сходства
7. Сохранение удерживает полные входы индекса сходства (`state_vector` / `state_features`) в профилях ожидания.

---

## Менеджер сна

Файл: `src/sleep.py`

### `SleepManager.sleep_cycle() -> dict`
Возвращает статистику воспроизведения и консолидации за цикл, включая:
- `replay_selected`, `replays`, `replay_blocked`
- `replay_diversity_index`
- `shock_replays`, `shock_frequency`
- `replay_confidence_mean`, `replay_stability_mean`
- `value_variance`, `value_variance_ratio`
- `total_value_delta_sleep`, `total_bg_delta_sleep`
- `sleep_update_count`
- `mean_ach_during_cycle`
- `mean_ach_above_baseline`
- метрики SAC:
  - `sac_episodes_gated`, `sac_actions_considered`, `sac_actions_updated`, `sac_actions_skipped`
  - `sac_rejected_*`
  - `sac_phase`, `phase_distribution`
  - `mean_sigma_change`, `mean_stability_change`, `structural_alert_count`
  - `semantic_drift_rate`, `stability_growth_rate`, `divergence_reduction_index`, `overconfidence_index`
- метрики синхронизации EDPC и SAC:
  - `edpc_sac_sync_enabled`, `edpc_sac_sync_phase`
  - `edpc_sac_sync_updates`, `edpc_sac_sync_conflicts`
  - `edpc_sac_sync_energy_used`, `edpc_sac_sync_skipped`
- диагностика присвоения кредита:
  - `eligibility_trace_mean`
  - `credit_window_usage`
  - `replay_causality_mean`
  - `anchor_source`
  - `reward_anchor_index`

### `SleepManager.deep_sleep(cycles=3) -> dict`
Агрегирует статистику циклов и средние:
- `mean_ach_during_cycle`
- `mean_ach_above_baseline`
- `value_variance_ratio`
- `mean_replay_diversity_index`
- `mean_replay_confidence`
- `mean_replay_stability`
- `eligibility_trace_mean`, `credit_window_usage`, `replay_causality_mean`
- `total_shock_replays`, `shock_frequency`
- агрегированные метрики SAC, распределение фаз и индексы дрейфа

### Жёсткие ограничения SAC (менеджер сна)
- Выполняется только в конвейере воспроизведения сна.
- `sac_alpha_slow <= 0.01` (нарушение вызывает `ValueError`).
- `sac_alpha_base <= 0.01` (нарушение вызывает `ValueError`).
- `sac_lambda_sws > sac_lambda_rem` (нарушение вызывает `ValueError`).
- Порог блокировки по среднему шоку (`sac_shock_block_threshold`) и минимальное число воспроизведений (`sac_replay_min_count`).
- Пол дисперсии против кристаллизации: `sac_sigma_floor` (по умолчанию `0.01`).
- Правило одной фазы на действие: на одно обновление действия применяется ровно одна фаза из `SWS/REM/TRANSITIONAL`.

### Присвоение кредита с привязкой к награде (Spec 011a)
1. Последовательность воспроизведения выбирает якорь с учётом награды:
   - явный якорь награды (если доступен)
   - откат к индексу сильнейшего TD-шока
   - откат к середине, когда нет ни якоря награды, ни якоря TD-шока
2. Причинная глубина считается по временной дистанции от якоря (а не по сырому порядку индексов воспроизведения).
3. Следы соответствия ограничены окном кредита воспроизведения и сводятся в диагностику цикла.

### Поведение фаз и исполнения SAC
- Классификатор фаз поддерживает глобальный режим и необязательный локальный режим (`local_phase_mode=True`).
- Глобальная фаза может выводиться из строк, которые фактически пригодны к обновлению (после допуска и предусловий обновления).
- Допуск SAC на уровне эпизода применяется до агрегации:
  - пороги уверенности, устойчивости, шока и вероятности консолидации
- Взвешивание воспроизведения гибридное:
  - `weight = replay_priority * confidence * stability * (1 - shock)`
- Устойчивость REM ограничена снизу величиной `sac_stability_floor_rem`.
- Жизненный цикл структурного предупреждения:
  - `meta["structural_alert"]` устанавливается в циклах структурного шока REM
  - предупреждение автоматически сбрасывается после `sac_structural_alert_reset_cycles` спокойных циклов
- Обновление семантической уверенности имеет ограниченный шаг за цикл:
  - `sac_semantic_confidence_step_cap`

---

## Хранилище

Файлы: `src/storage.py`, `src/state_codec.py`

### Формат на диске (issues #16 / #31)

Сохранения агента — документы UTF-8 JSON, не pickle.

| Поле | Значение |
|---|---|
| `format` | `nowa-agent-state` |
| `schema_version` | `1` (единственная версия, которую грузит эта сборка) |
| Расширение | `.nowa` (по умолчанию `agent_save_*.nowa`) |

`dump_state` / `load_state` в `state_codec.py` проверяют формат, отвергают байты pickle и пишут атомарно. Обёртки: `read_agent_state(path)`, `write_agent_state(path, state)`. Спека: [specs/issue-16-31-safe-agent-state.ru.md](specs/issue-16-31-safe-agent-state.ru.md).

Старые `.pkl` дают `StateFormatError` при load. Миграции нет.

### `AgentStorage.save_agent(...)` / `load_agent(...)`

В карте `state` — эпизоды гиппокампа и при поддержке `hippocampus_decision` из `export_persistent_state` (сигнатуры, novelty-кэши, окно событий; сигнатуры при load не пересобираются).

Также сохраняется:

1. Полная полезная нагрузка нейромодуляторов (`to_dict()`), включая ACh.
2. Слой ценности и фильтрованная консолидация (EDPC/SAC, `selector_action_metadata`).
3. `conflict_arbitration` и `intent_memory`, если переданы (GUI ядра передаёт оба вместе с `agent`).
4. Двухуровневая пластичность при `agent=`: `labile_layer`, `plasticity_config`, `host_clock_s`, `bg_outcome_slots`, `bg_action_channels`, BG sleep memories, lifetime/runtime/wakefulness/autonomous.
5. Циркадное бодрствование (`wakefulness`, `last_update_ts`, …).
6. Снимок автономной среды (`drives`, `energy`, `speech`, `tick_count`, `failures`).

После load `_bind_restored_two_tier(agent, sleep_manager)` перепривязывает managers к `labile` и `plasticity`.

**Не пишется:** гиперпараметры конструктора гиппокампа (ёмкость, decay при создании); живой объект сохраняет свои параметры.

### Чекпоинты песочницы и сотрудника

| Артефакт | Формат | Модуль |
|---|---|---|
| `*.ckpt` | `nowa-sandbox-checkpoint`, схема `2` | `Demo/Virtual company/src/nowa_sandbox/sandbox_checkpoint.py` |
| `*.ckpt.agent.nowa` | `nowa-agent-state`, схема `1` | то же (опционально `sandbox_intent_memory`) |
| `mind.nowa` | `nowa-agent-state`, схема `1` | `employee_checkpoint.py` (опционально `vc_intent_memory`) |

В метаданных песочницы — `GenomeVector.to_dict()`; эпигеном в файл чекпоинта не входит.

---

## Инварианты ядра

1. ACh непосредственно формулу ошибки TD не изменяет.
2. ACh альфу сна не масштабирует.
3. Значения автономности и бодрствования ограничены безопасными числовыми диапазонами.
4. Выдерживается период молчания автономной речи.
5. Формула полезности внутренней симуляции общая для селектора и среды исполнения.
6. Круговой проход сохранения и загрузки сохраняет согласованность состояния автономности и бодрствования.
7. Двойной модуляции аффекта и угрозы между давлением селектора и вентилем BG нет.
8. Усталость на основе бодрствования использует семантику `WakefulnessState.get_cognitive_reliability()`:
   `clamp(base_alertness - sleep_pressure + circadian_signal, 0..1)`.
   Унаследованный откат `(1 - wakefulness)` служит только совместимости.
9. `NO_ACTION` от таламического вентиля сохраняется (случайной подмены нет).
10. Веса стратегий, используемые селектором, суть нормированные вероятности (softmax).
11. Связь побуждения с политикой применяется модуляцией давления селектора, а обход вентиля BG не используется.
12. Отложенная обратная связь применяется только на наступившем шаге и после него.
13. ValueLayer хранит сырой сигнал награды и раскрывает диагностику обрезания для наблюдения насыщения.
14. Уверенность и устойчивость EDPC остаются в интервале `[0.0, 1.0]`.
15. Шок предсказания поднимается только когда превышены оба порога: уверенности и дельты.
16. Обновление фазы SAC выполняется только во сне, а правило фазы на уровне действия взаимно исключающее (`SWS xor REM xor TRANSITIONAL`).
17. Глобальная фаза SAC вычисляется по данным, фактически пригодным к обновлению (а не только по сырому потенциалу воспроизведения).
18. `prediction_shock_score` и `prediction_shock_flag` различны; `bool(score)` не используется.
19. Энергетический бюджет EDPC и SAC использует нормированную стоимость (`clamp(replay_priority, 0..1)`).
20. `conflict_flag` очищается в начале сна; `expectation_memory` ведётся как `OrderedDict`.
21. Неопределённость арбитража решения сглаживается EMA, а переход режима использует гистерезис.
22. Обдуманное планирование изменяет давление только в режиме `DELIBERATIVE`, до выбора BG и таламуса.
23. Планирование прогона использует эпизодических кандидатов, отфильтрованных по сходству, и ограниченные средства вычисления.
24. Древесное воображение HIE-003 имеет жёсткие пределы (`action_branching<=4`, `max_tree_nodes<=128`, `depth<=5`) и эпизодическую память не изменяет.
25. Резерв структурированного воображения HIE-002 хранит независимые жёсткие пределы (`samples/depth/branching/max_graph_nodes/max_graph_edges`).
26. Воображение планирования использует смесь (`memory` + `imagined`), а жёсткий `max(...)` не используется.
27. Уверенность структурированного воображения ограничена интервалом `[0.0, 1.0]`.
28. Глубина присвоения кредита привязана к награде (причинная дистанция), а наивный порядок позиций воспроизведения не используется.
29. Векторы генома сохраняют детерминированный порядок ключей и ограниченные диапазоны каждого гена на всех путях мутации, скрещивания и сериализации.


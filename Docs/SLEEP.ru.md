# Консолидация во сне (ядро NOWA)

English: [SLEEP.en.md](SLEEP.en.md)

Обзор уровней и контракт с хостом: [Docs/architecture/two-tier-plasticity.ru.md](../Docs/architecture/two-tier-plasticity.ru.md).

`Agent.sleep(cycles=...)` — единственная точка входа, открывающая `learning_allowed()` для записи в стабильный слой. Код: `src/agent.py`, `src/sleep.py` (`deep_sleep`, `_consolidate_two_tier_once`).

## Один сон — один проход на эпизод

В начале `deep_sleep`, **до** цикла `sleep_cycle`:

1. Затухание лабильных меток до часов хоста на засыпании.
2. Выбор эпизодов: известный исход, консолидация не закрыта.
3. Упорядочивание по **spec replay priority** (только для двухуровневой пачки, не внутри EDPC-счёта replay).
4. Для каждого эпизода:
   - **Capture** доли κ оставшегося лабильного тега Go/NoGo (`capture_kappa` = **0.5**).
   - **Компенсированный шаг:** `η_eff = 0.08 − 0.5×0.02 = **0.07**`; `g_DA = 1`. Незатухший `+1` без тега: **+0.07** на Go; с полным дневным тегом capture **+0.01** и шаг **+0.07** → **+0.08** (Go **0.5 → 0.58**).
   - **EMA привычки** на канале и `intent_memory.apply_outcome` с `affect_gain ∈ [0.25, 1.5]`.
   - Снятие лабильного вклада эпизода (Q в стабильную таблицу **не** копируется).
5. Внешние хуки обучения и медленный аффект из дневных буферов.
6. Перенос лабильных визитов в стабильные счётчики.

Затем `cycles` раз `sleep_cycle()` (replay TD только **стабильного Q**, кора, SHY, цепочки и т.д.). Потолки PR #35 сохраняются.

Каждый `sleep_cycle` продвигает канонический аффект на один срез симулированного времени сна (`SleepManager._affective_cycle_dt()`): по умолчанию **1800 с** за цикл или равные доли `sleep_duration_seconds` в `deep_sleep`. Вызовы — `AffectiveSpace.step(..., asleep=True)`; клиренс оси и возврат `baseline` к `baseline_setpoint` в **4×** быстрее бодрствования (`SLEEP_RECOVERY_SCALE`). См. [specs/issue-54-affect-simulated-time.ru.md](specs/issue-54-affect-simulated-time.ru.md).

После циклов — `consolidated = True`, `consolidated_reward`, `consolidated_revision`. Второй сон без новых эпизодов не меняет перечисленные поля отпечатка (кроме SHY при `cycles > 0`).

`sleep(cycles=0)` — только двухуровневый проход и пометка, без `sleep_cycle`.

## Приоритет replay (только порядок)

`1.0|δ| + 0.5|r| + 0.25·novelty + 0.25·salience`, δ по **стабильным** значениям; ничья по `episode_id`. Не добавляется в `_compute_replay_priority` для EDPC.

## Q, Go/NoGo, привычки

| Механизм | Что меняет |
|----------|------------|
| Лабильные метки днём | Быстрый сдвиг; затухание |
| Replay | Только **стабильный Q** |
| Capture + `η_eff` | **Стабильные** Go/NoGo |
| EMA + `apply_outcome` | **Стабильные** привычки |

## Ревизии и потери

- До первой консолидации — финальный лабильный вклад; одна запись во сне.
- После консолидации — **новое** наблюдение, без отката стабильного слоя.
- Вытеснение из гиппокампа — `lost_unconsolidated`, без стабильного эффекта.

## `PlasticityConfig`

См. таблицу в [SLEEP.en.md](SLEEP.en.md) и спеку #13 §6.

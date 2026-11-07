# Issue #24 — Тихие сбои: геном при зачатии, mortality, лимит популяции

English: [issue-24-silent-failures.en.md](issue-24-silent-failures.en.md)

Закрывает #24. PR #62. Связано: #15 (широкие обработчики исключений).

Затронуты когнитивное **ядро** (`src/mortality.py`, `src/swarm.py`) и хост демо **Colony chinchillas** (`colony_agent.py`, `simulation_runner.py`, `colony_swarm_bridge.py`). Коммит реализации: `f80a28a`.

---

## 1. Проблема

Три режима тихого сбоя подтверждены статическим разбором кода (issue #24, аудит `3c70385`):

| Сбой | Симптом |
| --- | --- |
| **Роды без отца среди живых** | `_give_birth` искал отца среди живых; при его смерти кроссовер пропускался, у потомства `genome is None`. |
| **Голый `except` вокруг mortality** | Любое исключение в `MortalitySystem.update` глоталось; агент мог оставаться живым бесконечно. |
| **Нетранзакционный `add_agent`** | После `self.agents.append(...)` сбой swarm `add_agent` и fallback runner давали повторный append → дубли только в списке колонии, не в swarm, вне проверки mortality. |

---

## 2. Решение и обоснование

**Решение:** устранить все три пути через явное логирование, снимок генома отца при зачатии, суженную обработку исключений и постановку в swarm до списка колонии.

**Обоснование:** размножение и смертность должны оставаться наблюдаемыми и согласованными с эволюцией (наследование даже если отец умер до родов). Лимит `MAX_POPULATION_SIZE = 256` должен проверяться до публикации слота и записи в списке колонии.

---

## 3. Поведение

### 3.1 Снимок при зачатии и рекомбинация при родах

При начале беременности (`_start_pregnancy` → `_capture_conception_genome`):

- У матери сохраняется независимая копия генома отца в `_conception_father_genome` (`_copy_genome`), плюс `_conception_father_id`, `_conception_father_name`, `_conception_father_generation`.
- Снимок — не тот же объект, что живой `father.genome`; замена или удаление генома отца позже не стирает снимок.

При родах (`_inherit_nowa_from` → `_father_genome_for_birth`):

- Для кроссовера сначала `_conception_father_genome`; при отсутствии снимка — `genome` живого отца.
- **Поколение** потомка: `max(mother.generation, father_generation) + 1`, где `father_generation` — у живого отца или из `_conception_father_generation` на пути снимка.
- **Фенотип / скалярное наследование** (энергия, social drive, affective decay и т.д.) по-прежнему читается у **живого** отца; мёртвый отец даёт вклад только через снимок генома.
- После `_give_birth` вызывается `_clear_conception_record`.

**Логи / исходы:**

| Условие | Результат |
| --- | --- |
| Есть геном матери и отцовский (снимок или живой) | Кроссовер + мутация; `genome_inheritance_meta["mode"] == "recombined"` |
| Исключение при кроссовере / apply | Warning `genome recombination failed for offspring of …` |
| Нет генома матери и/или отцовского | `offspring.genome is None`; warning `offspring of … born without a recombined genome (mother_genome=…, father_genome=…, father_id=…)` |

### 3.2 Mortality: суженные except и запасной lethal-путь

**Ядро** (`MortalitySystem`):

- Новый `apply_if_already_lethal(energy, wakefulness, lived_steps, biological_age_s)` — считает `_lethal_cause` без шага сенесценции (ошибка учёта не должна снимать уже летальное состояние).
- `_lethal_cause` объединяет: `exhaustion`, `sleep_deprivation`, `old_age`, `senescence` (vitality ≤ 0).

**Swarm** (`SwarmEnvironment._update_agent_vitality`) и **колония** (`ChinchillaAgent._apply_mortality`):

- `mortality.update(...)` в `except (TypeError, ValueError, AttributeError, ArithmeticError, RuntimeError)` с warning `mortality update failed for agent …; death check continues: …`.
- Затем `apply_if_already_lethal` с теми же energy / wakefulness / steps / age.
- В колонии: нечитаемая energy → `_energy_override` или **1.0**; нечитаемая wakefulness → **0.0**.

### 3.3 Транзакционное добавление в популяцию

**Swarm** (`SwarmEnvironment.add_agent`):

- `len(self._slots) >= MAX_POPULATION_SIZE` **до** создания слота.
- Размещение через `_find_free_position`; при ошибке — raise **до** появления слота.

**Runner** (`SimulationRunner.add_agent`):

- Сначала `self.swarm.add_agent(agent)`; `self.agents.append` только при успехе.
- Удалён дублирующий append при сбое swarm.

**Рождение** (`_spawn_pending_offspring`):

- Каждое потомство через `add_agent`; при `ValueError` / `RuntimeError` — warning `offspring … was not admitted to the colony: …`.
- `births_this_step` и `total_births` растут только для принятых; отклонённое при лимите отбрасывается (очереди нет).

---

## 4. Верификация

**Регрессии по issue**

| Набор | Файл | Фокус |
| --- | --- | --- |
| Ядро swarm | `tests/test_issue24_silent_failures.py` | Cap до публикации; откат при сбое размещения; mortality + удаление летального; сытого не убивать при разовой ошибке update |
| Хост колонии | `Demo/Colony chinchillas/tests/test_issue24_silent_failures.py` | Мёртвый отец + снимок; роды без геномов в логе; пути mortality; дубли при cap / placement; spawn на лимите |

**Зафиксированные прогоны (senior dev, коммит `f80a28a`):**

| Объём | Результат |
| --- | --- |
| Затронутые модули / регрессии issue | **73 passed** |
| Полный репозиторий | **1148 passed**, **5 skipped** |

---

## 5. Последствия

- Потомство отцов, умерших до родов, получает рекомбинированный геном при наличии снимка зачатия.
- Ошибки учёта mortality видны в логах; уже летальное состояние может завершиться через `apply_if_already_lethal`.
- Списки колонии и слоты swarm согласованы на лимите; счётчики рождений — только по принятым агентам.
- При `MAX_POPULATION_SIZE` новорождённые отбрасываются с записью в лог, без дублей и частичного admit.

---

## 6. Открытые вопросы

| Тема | Заметки |
| --- | --- |
| **Save/load колонии** | `ColonyStorage` не сохраняет `genome` и `_conception_father_genome` — в этом фиксе не делалось. |
| **Потомство на лимите (256)** | Сейчас: отказ и отбрасывание. Выбор продукта: ждать слот vs жёсткое удаление. |
| **`reproductive_system.update` / `register_reproduction`** | Широкий `except Exception: pass` вокруг `register_reproduction` в `_give_birth` без изменений (см. #15). |

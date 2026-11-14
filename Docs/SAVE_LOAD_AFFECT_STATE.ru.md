# Обновление: сохранение и загрузка состояния агента

English version: [SAVE_LOAD_AFFECT_STATE.en.md](SAVE_LOAD_AFFECT_STATE.en.md)

**Статус (27 сентября 2026 г.).** Документ ядра. Актуальное научное изложение комплекса на русском и английском языках приведено в [SCIENTIFIC_DESCRIPTION.ru.md](SCIENTIFIC_DESCRIPTION.ru.md). Текст ниже сохраняет формулировки исходной редакции: это нормативный контракт модуля либо лабораторная запись.


**Дата**: 8 февраля 2026  
**Статус**: ЗАВЕРШЕНО И ПРОТЕСТИРОВАНО

---

## Что было добавлено

Реализована полная поддержка сохранения и загрузки:
- аффективного состояния
- аффективных следов (Phase 3.5)
- нейромодуляторов
- времени жизни агента

---

## Внесённые изменения

### 1. **src/storage.py** — обновление функций сохранения и загрузки

#### Добавлен импорт
```python
from affect import AffectiveState
```

#### Функция `save_agent()` — теперь сохраняет affect_state, следы и время жизни
```python
def save_agent(self, hippocampus, cortex, selector, affect_state=None,
               temporal=None, sleep_manager=None, neuromodulators=None,
               affective_persistence=None, filename=None, agent=None):
    """Сохранить состояние агента в файл"""
    # ... existing code ...
    
    # Сохранить аффективное состояние если оно есть
    if affect_state is not None:
        agent_state["affect_state"] = {
            "valence": affect_state.valence,
            "arousal": affect_state.arousal,
            "threat": affect_state.threat,
            "curiosity": affect_state.curiosity
        }

    # Новое: сохранить affective traces (Phase 3.5)
    if affective_persistence is not None:
        agent_state["affective_persistence"] = affective_persistence.to_dict()

    # Новое: сохранить lifetime агента
    if agent is not None:
        agent_state["agent_lifetime"] = {
            "created_ts": agent.created_ts,
            "simulated_sleep_seconds": agent._simulated_sleep_seconds
        }
```

**Изменения**:
- Добавлен параметр `affect_state=None`
- Добавлен параметр `affective_persistence=None`
- Добавлен параметр `agent=None`
- Сохраняются все 4 параметра аффективного состояния
- Обратная совместимость сохранена (параметр опциональный)

#### Функция `load_agent()` — теперь загружает affect_state, следы и время жизни
```python
def load_agent(self, hippocampus, cortex, selector, filepath, affect_state=None,
               temporal=None, sleep_manager=None, affective_persistence=None, agent=None):
    """Загрузить состояние агента из файла"""
    # ... existing code ...
    
    # Восстановить аффективное состояние если оно сохранено
    if affect_state is not None and "affect_state" in agent_state:
        affect_data = agent_state["affect_state"]
        affect_state.valence = affect_data["valence"]
        affect_state.arousal = affect_data["arousal"]
        affect_state.threat = affect_data["threat"]
        affect_state.curiosity = affect_data["curiosity"]

    # Новое: Восстановить affective traces
    if affective_persistence is not None and "affective_persistence" in agent_state:
        affective_persistence.from_dict(agent_state["affective_persistence"])

    # Новое: Восстановить lifetime агента
    if agent is not None and "agent_lifetime" in agent_state:
        agent.created_ts = agent_state["agent_lifetime"]["created_ts"]
        agent._simulated_sleep_seconds = agent_state["agent_lifetime"]["simulated_sleep_seconds"]
```

**Изменения**:
- Добавлен параметр `affect_state=None`
- Добавлен параметр `affective_persistence=None`
- Добавлен параметр `agent=None`
- Восстанавливаются все 4 параметра аффективного состояния
- Обратная совместимость сохранена (параметр опциональный)

### 2. **src/gui.py** — обновление вызовов в интерфейсе

#### Функция `save_state()` — теперь передаёт affect_state, следы и агента
```python
def save_state(self):
    """Сохранить состояние агента"""
    try:
        filepath = self.storage.save_agent(
            self.hippocampus,
            self.cortex,
            self.selector,
            affect_state=self.agent.affect_state,          # ← сохраняем affect
            affective_persistence=self.agent.affective_persistence,  # ← traces
            agent=self.agent  # ← lifetime
        )
```

#### Функция `load_state()` — теперь загружает affect_state, следы и агента
```python
def load_selected():
    # ...
    timestamp = self.storage.load_agent(
        self.hippocampus,
        self.cortex,
        self.selector,
        selected_save['path'],
        affect_state=self.agent.affect_state,           # ← affect
        affective_persistence=self.agent.affective_persistence,  # ← traces
        agent=self.agent  # ← lifetime
    )
    # ...
    self.update_affect_display()  # ← Обновляем визуализацию
```

---

## Тестирование

Создан новый файл `test_save_load_affect.py` с 8 тестами:

### Результаты тестов

```
Тест 1: Начальное аффективное состояние
   - Проверка инициализации параметров

Тест 2: Обновление аффективного состояния
   - Проверка update_from_reward() и update_from_novelty()

Тест 3: Сохранение состояния с affect_state
   - Проверка создания файла с аффективными параметрами

Тест 4: Изменение состояния перед загрузкой
   - Проверка успешного изменения valence

Тест 5: Загрузка состояния с восстановлением affect_state
   - Проверка восстановления значений

Тест 6: Проверка корректности восстановления
   - Проверка точности восстановления всех параметров

Тест 7: Загрузка в исходный agent.affect_state
   - Проверка восстановления в agent.affect_state

Тест 8: Загрузка без affect_state (обратная совместимость)
   - Проверка работы старого программного интерфейса

Результат: ВСЕ 8 ТЕСТОВ ПРОЙДЕНЫ

Добавлены новые тесты:
- `tests/test_affective_persistence.py`
- `tests/test_agent_lifetime_save_load.py`
```

### Все существующие тесты по-прежнему проходят

```
test_affective_regulators.py: 25/25 PASSED
test_affect_integration.py: 12/12 PASSED
─────────────────────────────────────
ИТОГО: 37/37 PASSED
```

---

## Процесс сохранения и загрузки

### Сохранение

```
Пользователь нажимает «Сохранить состояние»
        ↓
GUI.save_state() вызывает storage.save_agent()
        ↓
storage.save_agent() сохраняет:
  ├─ hippocampus.experiences
  ├─ cortex.patterns
  ├─ selector.actions и confidence_threshold
  └─ affect_state (valence, arousal, threat, curiosity) ← НОВОЕ
  ├─ affective_persistence (следы) ← НОВОЕ
  └─ agent_lifetime (created_ts, simulated_sleep_seconds) ← НОВОЕ
        ↓
Файл сохраняется в UTF-8 JSON (`nowa-agent-state`, схема `1`, `.nowa`). Pickle не используется; старые `.pkl` отвергаются.
        ↓
Интерфейс показывает: «Состояние сохранено»
```

### Загрузка

```
Пользователь выбирает файл и нажимает «Загрузить»
        ↓
GUI.load_state() вызывает storage.load_agent()
        ↓
storage.load_agent() восстанавливает:
  ├─ hippocampus.experiences
  ├─ cortex.patterns
  ├─ selector.actions и confidence_threshold
  └─ affect_state (valence, arousal, threat, curiosity) ← НОВОЕ
  ├─ affective_persistence (следы) ← НОВОЕ
  └─ agent_lifetime (created_ts, simulated_sleep_seconds) ← НОВОЕ
        ↓
Интерфейс вызывает update_affect_display()
        ↓
Визуализация обновляется загруженными значениями
        ↓
Интерфейс показывает: «Состояние загружено»
```

---

## Проверочный список

- [x] Функция `save_agent()` сохраняет affect_state
- [x] Функция `load_agent()` загружает affect_state
- [x] Интерфейс передаёт affect_state при сохранении
- [x] Интерфейс передаёт affect_state при загрузке
- [x] Интерфейс передаёт affective_persistence при сохранении
- [x] Интерфейс передаёт affective_persistence при загрузке
- [x] Интерфейс передаёт агента при сохранении и загрузке
- [x] Интерфейс обновляет визуализацию после загрузки
- [x] Обратная совместимость сохранена
- [x] Все 8 новых тестов проходят
- [x] Все 37 существующих тестов проходят
- [x] Нет регрессий

---

## Статистика

```
Файлы изменены:     2
  ├─ src/storage.py (добавлены параметры и время жизни)
  └─ src/gui.py (обновлены вызовы сохранения и загрузки)

Файлы созданы:      1
  └─ test_agent_lifetime_save_load.py (новый тест)

Новые тесты:        2 (аффективная устойчивость и время жизни)

Регрессии:          0
```

---

## Результат

Теперь при сохранении агента:
- Сохраняется аффективное состояние
- Сохраняются аффективные следы
- Сохраняется время жизни агента
- При загрузке восстанавливается состояние
- Визуализация интерфейса обновляется корректно
- Обратная совместимость сохранена
- Полностью протестировано

**Статус**: **ГОТОВО К ИСПОЛЬЗОВАНИЮ**

---

## Как использовать

### В интерфейсе
1. Нажимаете «Сохранить» — сохраняется affect_state
2. Нажимаете «Загрузить» — загружается affect_state
3. Визуализация обновляется автоматически

### Программно
```python
# Сохранение
storage.save_agent(
    hippocampus, cortex, selector,
    affect_state=agent.affect_state,
    affective_persistence=agent.affective_persistence,
    agent=agent
)

# Загрузка
storage.load_agent(
    hippocampus, cortex, selector, filepath,
    affect_state=agent.affect_state,
    affective_persistence=agent.affective_persistence,
    agent=agent
)
```

---

**Дата обновления**: 8 февраля 2026  
**Версия**: 1.2  
**Статус**: ГОТОВО К ПРОИЗВОДСТВЕННОМУ ИСПОЛЬЗОВАНИЮ

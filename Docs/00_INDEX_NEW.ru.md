# Документация проекта NOWA-Cognitive

English version: [00_INDEX_NEW.en.md](00_INDEX_NEW.en.md)

**Статус (27 сентября 2026 г.).** Указатель устарел. Порядок чтения: [INDEX.ru.md](INDEX.ru.md) и [SCIENTIFIC_DESCRIPTION.ru.md](SCIENTIFIC_DESCRIPTION.ru.md).

**Версия:** 2.2
**Последнее обновление:** февраль 2026 г.
**Состояние:** готовность к промышленной эксплуатации — фаза 3 завершена

---

## Структура документации

### Начало работы

- **[START_HERE.md](START_HERE.ru.md)** — двуязычная точка входа — обновлено
- **[QUICK_START.md](QUICK_START.ru.md)** — запуск за 5 минут — новый
- **[QUICK_START_RU.md](QUICK_START_RU.ru.md)** — краткое руководство
- **[INSTALLATION.ru.md](INSTALLATION.ru.md)** — установка и настройка

### Архитектура и устройство

- **[ARCHITECTURE.md](ARCHITECTURE.ru.md)** — общая архитектура системы
- **[DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.ru.md)** — полное руководство разработчика с примерами — новый
- **[PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.ru.md)** — структура каталогов проекта
- **[EXECUTIVE_SUMMARY.md](EXECUTIVE_SUMMARY.ru.md)** — обзор системы верхнего уровня

### Основные компоненты

#### Фаза 1: основание
- Аффективная система (`AffectiveState`)
- Система нейромодуляторов (`NeuromodulatorState`)
- Базовое порождение действий

#### Фаза 2: расширенные возможности
- **[README_AFFECTIVE_SYSTEM.md](README_AFFECTIVE_SYSTEM.ru.md)** — аффективная регуляция
- **[Phase2_Wakefulness_PFC_Extension.md](Phase2_Wakefulness_PFC_Extension.ru.md)** — бодрствование и префронтальная кора
- **[spec_circadian_process_c.md](spec_circadian_process_c.ru.md)** — циркадный процесс C для модели бодрствования
- **[NEUROMODULATORS_QUICK_REFERENCE.md](NEUROMODULATORS_QUICK_REFERENCE.ru.md)** — справочник нейромодуляторов

#### Фаза 3: базальные ганглии (февраль 2026 г.)
- **[PHASE_3_GUIDE.md](PHASE_3_GUIDE.ru.md)** — полное руководство по фазе 3 — новый
- **[Phase_3_Basal_Ganglia_Action_Gating_refactoring.md](Phase_3_Basal_Ganglia_Action_Gating_refactoring.ru.md)** — спецификация базальных ганглиев
- **[REFACTORING_REPORT.md](../REFACTORING_REPORT.md)** — полный отчёт о рефакторинге
- **[REFACTORING_SUMMARY.py](../REFACTORING_SUMMARY.py)** — краткая сводка (исполняемая)

### Тестирование и разработка
- **[TESTING.ru.md](TESTING.ru.md)** — руководство по тестированию
- **[DEVELOPMENT.md](DEVELOPMENT.ru.md)** — руководство по разработке
- **[CHANGELOG.md](CHANGELOG.ru.md)** — журнал изменений проекта

### Справочник интерфейса
- **[API.md](API.ru.md)** — полная документация интерфейса

### Отчёты и состояние
- **[PROJECT_STATUS_FINAL.ru.md](PROJECT_STATUS_FINAL.ru.md)** — текущее состояние проекта
- **[PROJECT_STATISTICS.md](PROJECT_STATISTICS.ru.md)** — метрики и статистика проекта
- **[PROJECT_PROGRESS.md](PROJECT_PROGRESS.ru.md)** — ход разработки

---

## Быстрая навигация по роли

### Для новых разработчиков
1. Прочитать [START_HERE.md](START_HERE.ru.md) — обновлено, двуязычное содержание
2. Пройти [QUICK_START.md](QUICK_START.ru.md) — запуск за 5 минут
3. Прочитать [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.ru.md) — полное руководство
4. Просмотреть [ARCHITECTURE.md](ARCHITECTURE.ru.md)
5. Изучить [PHASE_3_GUIDE.md](PHASE_3_GUIDE.ru.md)

### Для архитекторов системы
1. Просмотреть [ARCHITECTURE.md](ARCHITECTURE.ru.md)
2. Изучить [EXECUTIVE_SUMMARY.md](EXECUTIVE_SUMMARY.ru.md)
3. Проверить [PHASE_3_GUIDE.md](PHASE_3_GUIDE.ru.md)
4. Просмотреть [API.md](API.ru.md)

### Для контроля качества и тестировщиков
1. Прочитать [TESTING.ru.md](TESTING.ru.md)
2. Просмотреть [PROJECT_STATISTICS.md](PROJECT_STATISTICS.ru.md)
3. Проверить [FULL_PROJECT_TEST_REPORT.md](FULL_PROJECT_TEST_REPORT.ru.md)

### Для развёртывания
1. Прочитать [INSTALLATION.ru.md](INSTALLATION.ru.md)
2. Просмотреть [PROJECT_STATUS_FINAL.ru.md](PROJECT_STATUS_FINAL.ru.md)
3. Проверить [DEVELOPMENT.md](DEVELOPMENT.ru.md)

---

## Фаза 3: базальные ганглии (последняя — февраль 2026 г.)

### Что такое фаза 3?
Фаза 3 реализует систему **стробирования действий базальными ганглиями** (`Basal Ganglia Action Gating`) — биологически правдоподобный механизм выбора действия, который включает:

- **Соревнование Go/NoGo:** действия соревнуются по конкурирующим каналам
- **Модуляция нейромодуляторами:** дофамин, кортизол, серотонин, норадреналин
- **Совет префронтальной коры:** кора может предлагать, но не диктовать
- **Двухуровневая пластичность:** лабильные смещения Q/Go/NoGo днём; стабильные значения, привычки и каналы консолидируются во сне
- **Сила привычки:** выученное поведение влияет на последующий выбор (вес: ×0.3)

### Ключевые документы
- [QUICK_START.md](QUICK_START.ru.md) — начать за 5 минут
- [PHASE_3_GUIDE.md](PHASE_3_GUIDE.ru.md) — полное руководство по фазе 3 — новый
- [Phase_3_Basal_Ganglia_Action_Gating_refactoring.md](Phase_3_Basal_Ganglia_Action_Gating_refactoring.ru.md) — спецификация
- [REFACTORING_REPORT.md](../REFACTORING_REPORT.md) — полный отчёт о реализации
- [FINAL_RESULT.txt](../FINAL_RESULT.txt) — краткая сводка

### Результаты тестов
- **29/29** тестов фазы 3 пройдены
- **279/279** тестов проекта пройдены
- **0** отказов тестов
- **100%** соответствие спецификации

### Ключевая формула
```
Net = Go - 0.5×NoGo + PFC_pressure + habit_strength×0.3

Where:
- Go = go_weight × dopamine × (1 + norepinephrine)
- NoGo = nogo_weight × cortisol
- PFC_pressure = prefrontal cortex advisory signal
- habit_strength = learned behavior strength (0-1)
```

---

## Компоненты системы

### Основные классы
```
src/
├── agent.py                 # Main agent class
├── affect.py               # AffectiveState
├── neuromodulators.py      # NeuromodulatorState
├── wakefulness.py          # WakefulnessState
├── basal_ganglia.py        # Phase 3 - BG system (600+ lines)
├── memory.py               # Memory systems
├── intent_memory.py        # Intent-based memory
└── gui.py                  # GUI visualization
```

### Набор тестов
```
tests/
├── test_basal_ganglia.py   # Phase 3 tests (29 tests) ✅
├── test_agent.py           # Agent integration
├── test_affect.py
├── test_neuromodulators.py
├── test_wakefulness.py
└── ... (250+ total tests)
```

---

## Быстрый старт

### Установка
```bash
# Navigate to project
cd e:\git\NOWA-Cognitive

# Install dependencies
pip install -r requirements.txt

# Verify installation
pytest tests/ -q
# Expected: 279 passed in ~1.5s ✅
```

### Запуск демонстрации интерфейса
```bash
python src/gui.py
```

### Первая программа
```python
from src.agent import Agent

# Create agent
agent = Agent(agent_name="MyBot")

# Register actions
agent.register_action_channel("attack", go_weight=0.8, nogo_weight=0.2)
agent.register_action_channel("defend", go_weight=0.5, nogo_weight=0.5)

# Let Basal Ganglia choose
action = agent.choose_action_via_basal_ganglia(pfc_pressure=1.0)
print(f"Agent chose: {action}")

# Record outcome and learn
agent.record_action_outcome(action, success=True, dopamine=1.5)

# Sleep to consolidate learning
agent.sleep()
```

Дополнительные примеры — в [QUICK_START.md](QUICK_START.ru.md).

---

## Статистика проекта

| Метрика | Значение |
|---------|----------|
| **Всего тестов** | 279 |
| **Тесты фазы 3** | 29 |
| **Доля успешных** | 100% |
| **Отказы тестов** | 0 |
| **Версия Python** | 3.13+ |
| **Основных классов** | 20+ |
| **Завершённых фаз** | 3 |
| **Файлов документации** | 70+ |
| **Строк кода** | 5 000+ |

---

## Последние изменения (фаза 3 — февраль 2026 г.)

### Рефакторинг завершён
- В формулу выбора действия добавлен `habit_strength`
- Тесты базальных ганглиев обновлены на устойчивость
- Подготовлена новая документация
- 100% соответствие спецификации
- Нуль регрессий (279/279 тестов проходят)

### Новая документация
- [START_HERE.md](START_HERE.ru.md) — обновлено до двуязычного вида
- [QUICK_START.md](QUICK_START.ru.md) — запуск за 5 минут
- [PHASE_3_GUIDE.md](PHASE_3_GUIDE.ru.md) — полное руководство по фазе 3
- [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.ru.md) — справочник разработчика
- [00_INDEX.md](00_INDEX.ru.md) — обновлённый указатель навигации

### Формула обновлена
```python
# Before (Phase 2):
Net = Go - 0.5*NoGo + PFC_pressure*wake_mod

# After (Phase 3 - with habit integration):
Net = Go - 0.5*NoGo + PFC_pressure*wake_mod + habit_strength*0.3
```

---

## Поддержка и участие

По вопросам, замечаниям и вкладу:
1. См. [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.ru.md)
2. Просмотреть [TESTING.ru.md](TESTING.ru.md)
3. См. [DEVELOPMENT.md](DEVELOPMENT.ru.md)
4. Проверить [CHANGELOG.md](CHANGELOG.ru.md)

---

## Организация файлов

Вся документация собрана в каталоге `Docs/`:
- документы архитектуры и устройства
- руководства по отдельным компонентам
- справочник интерфейса
- руководства по тестированию и разработке
- отчёты о состоянии и журналы изменений

**Расположение:** `e:\git\NOWA-Cognitive\Docs\`

---

## Рекомендуемый порядок чтения

### Короткий путь (30 минут)
1. **[START_HERE.md](START_HERE.ru.md)** — обзор (5 мин)
2. **[QUICK_START.md](QUICK_START.ru.md)** — запуск (5 мин)
3. **Запустить интерфейс** — увидеть работу (5 мин)
4. **[PHASE_3_GUIDE.md](PHASE_3_GUIDE.ru.md)** — фаза 3 (15 мин)

### Полный путь (2 часа и более)
1. **[START_HERE.md](START_HERE.ru.md)** — обзор и введение
2. **[QUICK_START.md](QUICK_START.ru.md)** — быстрый запуск
3. **[PHASE_3_GUIDE.md](PHASE_3_GUIDE.ru.md)** — подробности последней возможности
4. **[DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.ru.md)** — справочник разработчика
5. **[ARCHITECTURE.md](ARCHITECTURE.ru.md)** — устройство
6. **[API.md](API.ru.md)** — программный справочник
7. **[TESTING.ru.md](TESTING.ru.md)** — как тестировать
8. **[DEVELOPMENT.md](DEVELOPMENT.ru.md)** — как участвовать

---

## Ключевые документы по цели

### «Хочу понять систему» (45 мин)
1. [ARCHITECTURE.md](ARCHITECTURE.ru.md) — устройство системы
2. [PHASE_3_GUIDE.md](PHASE_3_GUIDE.ru.md) — подробности фазы 3
3. [API.md](API.ru.md) — справочник интерфейса

### «Хочу писать код» (2 часа)
1. [QUICK_START.md](QUICK_START.ru.md) — начать
2. [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.ru.md) — руководство с примерами
3. Исходный код в `src/`
4. Тесты в `tests/`

### «Хочу расширить систему» (3 часа и более)
1. [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.ru.md) — полное руководство
2. [ARCHITECTURE.md](ARCHITECTURE.ru.md) — устройство системы
3. [PHASE_3_GUIDE.md](PHASE_3_GUIDE.ru.md) — подробности фазы 3
4. Прочитать и изучить исходный код
5. Написать тесты (см. [TESTING.ru.md](TESTING.ru.md))

### «Нужно проверить, что всё работает»
1. [PROJECT_STATUS_FINAL.ru.md](PROJECT_STATUS_FINAL.ru.md) — отчёт о состоянии
2. [PROJECT_STATISTICS.md](PROJECT_STATISTICS.ru.md) — статистика тестов
3. Запустить: `pytest tests/ -q` — должны пройти все 279 тестов

---

## Следующие шаги (выберите один)

### Увидеть работу сразу
```bash
python src/gui.py
```
Оценка времени: 2 минуты

### Писать код
Следовать [QUICK_START.md](QUICK_START.ru.md)
Оценка времени: 5 минут

### Изучить основательно
Следовать «полному пути» выше
Оценка времени: 2 часа и более

### Глубокое понимание
1. Полный путь
2. Прочитать исходный код в `src/`
3. Просмотреть все тесты в `tests/`
Оценка времени: 4 часа и более

---

## Проверочный список

Убедитесь, что можете:
- [ ] Запустить: `pytest tests/ -q` → показывает 279 пройденных
- [ ] Запустить: `python src/gui.py` → открывается интерфейс
- [ ] Понять примеры в [QUICK_START.md](QUICK_START.ru.md)
- [ ] Написать первого агента (следуя краткому руководству)
- [ ] Знать, где расположена вся документация

---

**Последнее обновление:** февраль 2026 г.
**Версия:** 2.2
**Состояние:** готовность к промышленной эксплуатации — фаза 3 завершена

Разработка завершена. Система полностью документирована и протестирована.

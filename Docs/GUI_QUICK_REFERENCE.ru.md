# Краткий справочник графического интерфейса — когнитивная архитектура NOWA

English version: [GUI_QUICK_REFERENCE.en.md](GUI_QUICK_REFERENCE.en.md)

**Статус (27 сентября 2026 г.).** Документ ядра. Актуальное научное изложение комплекса на русском и английском языках приведено в [SCIENTIFIC_DESCRIPTION.ru.md](SCIENTIFIC_DESCRIPTION.ru.md). Текст ниже сохраняет формулировки исходной редакции: это нормативный контракт модуля либо лабораторная запись.


## Что изменилось

| Возможность | Прежде | Теперь |
|-------------|--------|--------|
| Обучение | Во время бодрствования | Только во время сна |
| Селектор | Обучаемые веса | Необучаемый, на основе давления |
| Обратная связь | Прямое обновление весов | Сохранение опыта с интенсивностью |
| Тренировка | Эпохи и точность | Циклы консолидации во сне |
| Статистика | Визуализация весов | Метрики консолидации |
| Инспектор | 4 вкладки | 5 вкладок (добавлена консолидация) |

---

## Новые кнопки и диалоги

### Кнопка сна
```
Button: 🌙 Сон
Purpose: Trigger consolidation of experiences to patterns
Opens: Sleep consolidation dialog
```

### Диалог сна
Показывает:
- Состояние до сна (опыты, паттерны, циклы)
- Конфигурацию (циклы: 1–10)
- Результаты после сна (консолидировано, кластеры, забыто)

---

## Инспектор из пяти вкладок

1. **Эпизодическая память**
   - Опыты в гиппокампе
   - Сигнатура, интенсивность, подкрепление

2. **Семантическая память**
   - Паттерны, созданные сном
   - Появляются только после сна

3. **Выбор действий**
   - У селектора нет весов
   - Основан на давлении (не обучается)

4. **Консолидация**
   - Конвейер сна: воспроизведение → кластеризация → консолидация → забывание
   - Показывает коэффициент консолидации

5. **Статистика**
   - Общее состояние агента
   - Циклы консолидации
   - Метрики памяти

---

## Шкала обратной связи

Обозначение → интенсивность (используется для обучения во сне):
- 😞 = 0.2 (очень плохо)
- 😐 = 0.4 (плохо)
- 🙂 = 0.6 (нейтрально)
- 😊 = 0.8 (хорошо)
- 😍 = 1.0 (отлично)

Сообщение: "💾 Опыт сохранен. Используйте 🌙 Сон для консолидации."

---

## Рабочий порядок

```
1. TYPE MESSAGE
   ↓
2. AGENT RESPONDS
   ↓
3. RATE RESPONSE (😊)
   ↓
4. EXPERIENCE STORED (intensity=0.8)
   ↓
5. CLICK 🌙 СОН
   ↓
6. CONSOLIDATION HAPPENS
   - Experiences clustered
   - Patterns created
   - Cycles incremented
   ↓
7. TYPE MESSAGE AGAIN
   ↓
8. BEHAVIOR CHANGED (from consolidated patterns!)
```

---

## Устаревшие возможности

### «Тренировка»
```
OLD: Click → Train selector with epochs
NEW: Shows warning:
  "Функция устарела. В NOWA обучение происходит ТОЛЬКО во время сна.
   Используйте 🌙 Сон!"
```

### «Авто-тренировка»
```
Same deprecation warning
```

---

## Отличия от прежнего интерфейса

### Прежний порядок
```
User Input
  ↓
Agent step
  ↓
Rating given
  ↓
Selector.learn() ← Weight optimization
  ↓
Behavior changes immediately (from new weights)
```

### Новый порядок
```
User Input
  ↓
Agent step (episodes + labile offsets)
  ↓
Rating given → Intensity (0.2-1.0)
  ↓
Experience stored (immutable)
  ↓
🌙 Sleep button
  ↓
Sleep consolidation:
  - Replay experiences
  - Cluster similar
  - Create patterns
  - Forget unstable
  ↓
Next user input
  ↓
Behavior changes (from consolidated patterns)
```

---

## Отображение статистики

### Прежде
```
Последнее действие: ...
Всего действий: ...
Средний вес: 0.123
```

### Теперь
```
Последнее действие: ...
Гиппокамп (шт): 5
Кортекс (шт): 2
Циклы сна: 3
```

---

## Отображение памяти

### Эпизодическая память (гиппокамп)
```
Эпизодическая память:
  Опытов: 5
  Ср. подкр.: 1.2
```
Показывает недавние опыты и число подкреплений.

### Семантическая память (кортекс)
```
Семантическая память:
  Паттернов: 2
  Ср. сила: 0.85
```
Показывает консолидированные паттерны, созданные сном.

---

## Весов больше нет

### Селектор теперь
```python
selector.choose([experiences], [patterns])
  ↓
Calculates pressure from experience activation
  ↓
Uses confidence threshold (0.7)
  ↓
Deterministic if confident
Stochastic if uncertain
  ↓
NO weights updated!
```

### Селектор прежде
```python
selector.choose(context, learned_weights)
  ↓
selector.learn(action, reward)  ← Direct weight update
  ↓
Weights change immediately
```

---

## Загрузка наборов данных

```
Click: Загрузить датасет
  ↓
Choose: Folder / File / From datasets/
  ↓
Experiences go to: Hippocampus
  (NOT directly to cortex anymore!)
  ↓
Shows: "✅ Загружено N опытов"
  ↓
Ready for: 🌙 Sleep consolidation
```

---

## Процесс консолидации

Во время сна опыты:

1. **Воспроизводятся** — активация усиливается
2. **Кластеризуются** — сходные опыты группируются
3. **Консолидируются** — кластеры становятся семантическими паттернами
4. **Забываются** — неустойчивые следы удаляются

Результат: кортикальные паттерны, которые направляют последующее поведение.

---

## Проверка хода работы

### До сна
```
Click: Инспектор
→ Tab "Семантическая память"
→ See: 0 paттернов (empty)
```

### После сна
```
Click: Инспектор
→ Tab "Семантическая память"
→ See: 3+ паттерна (patterns created!)
→ Tab "Консолидация"
→ See: "Циклов сна: 1"
```

---

## Типовые задачи

### Задача 1. Загрузить обучающие данные
```
1. Click: Загрузить датасет
2. Choose: JSON files
3. System: Loads to hippocampus
4. Status: Shows "✅ Loaded N experiences"
```

### Задача 2. Обучить на данных (сон)
```
1. Click: 🌙 Сон
2. Set: 3 cycles
3. System: Consolidates experiences
4. Result: Patterns created
5. Status: Shows consolidation stats
```

### Задача 3. Сохранить состояние
```
1. Click: Сохранить
2. System: Saves hippocampus, cortex, selector
3. Status: Shows "✅ Состояние сохранено"
```

### Задача 4. Просмотреть сведения о консолидации
```
1. Click: Инспектор
2. Tab 4: Консолидация
3. View: Sleep pipeline details
4. See: Consolidation ratio (patterns/experiences)
```

---

## Устранение затруднений

### Паттерны не появляются
```
Q: Why are there 0 patterns in "Семантическая память"?
A: Patterns only appear after sleep consolidation!
   Click 🌙 Сон to create patterns.
```

### Поведение не меняется
```
Q: Why does agent always choose the same action?
A: Need more sleep cycles to consolidate diverse patterns.
   Click 🌙 Сон → Set cycles: 5 or more
   Then try again.
```

### Опыты не сохраняются
```
Q: Where did my feedback go?
A: Stored in hippocampus with intensity value.
   Check: Инспектор → "Эпизодическая память"
```

### Ошибка импорта
```
Q: "ModuleNotFoundError: No module named 'sleep'"
A: Make sure you're in src/ directory or have correct path
   python -m src.gui  (from project root)
```

---

## Следует помнить

### Основной принцип
> **Поведение не выучивается. Оно возникает из опыта и сна.**

### Три правила
1. **Бодрствование** = сохранение опытов (без обучения)
2. **Сон** = консолидация стабильного слоя (Q, каналы, привычки, кора)
3. **Выбор** = на основе давления (без весов)

### Подтверждение
- У селектора нет атрибута `weights`
- У селектора нет метода `learn()`
- Всё обучение сосредоточено в `SleepManager` (только консолидация)
- Паттерны появляются только после сна
- Поведение возникает из консолидации

---

**NOWA GUI 2.0 — редакция когнитивной архитектуры**

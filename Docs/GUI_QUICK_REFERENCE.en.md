# GUI Quick Reference - NOWA Cognitive Architecture

Russian version: [GUI_QUICK_REFERENCE.ru.md](GUI_QUICK_REFERENCE.ru.md)

**Status (27 September 2026).** A core document. The current scientific exposition of the complex, in Russian and in English, is [SCIENTIFIC_DESCRIPTION.en.md](SCIENTIFIC_DESCRIPTION.en.md). The text below retains the wording of its original drafting: a normative module contract or a laboratory record.


## 🎯 What Changed

| Feature | Before | After |
|---------|--------|-------|
| Learning | During waking | Only during sleep |
| Selector | Learnable weights | Non-learnable pressure-based |
| Feedback | Direct weight update | Store experience with intensity |
| Training | Epochs + accuracy | Sleep consolidation cycles |
| Stats | Weights visualization | Consolidation metrics |
| Inspector | 4 tabs | 5 tabs (added consolidation) |

---

## 🌙 New Buttons & Dialogs

### Sleep Button
```
Button: 🌙 Сон
Purpose: Trigger consolidation of experiences to patterns
Opens: Sleep consolidation dialog
```

### Sleep Dialog
Shows:
- Status before sleep (experiences, patterns, cycles)
- Configuration (cycles: 1-10)
- Results after sleep (consolidated, clusters, forgotten)

---

## 5-Tab Inspector

1. **Episodic memory** (`Эпизодическая память`)
   - Experiences in hippocampus
   - Signature, intensity, reinforcement

2. **Semantic memory** (`Семантическая память`)
   - Patterns created by sleep
   - ⚠️ Only appear after sleep!

3. **Action selection** (`Выбор действий`)
   - Selector has NO weights
   - Pressure-based (not learnable)

4. **Consolidation** (`Консолидация`)
   - Sleep pipeline: replay → cluster → consolidate → forget
   - Shows consolidation ratio

5. **Statistics** (`Статистика`)
   - Overall agent state
   - Consolidation cycles
   - Memory metrics

---

## Feedback Scale

Emoji → Intensity (used for learning in sleep):
- 😞 = 0.2 (very poor)
- 😐 = 0.4 (poor)
- 🙂 = 0.6 (neutral)
- 😊 = 0.8 (good)
- 😍 = 1.0 (excellent)

Message: "💾 Опыт сохранен. Используйте 🌙 Сон для консолидации."

---

## Workflow

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

## Deprecated Features

### ❌ Training (`Тренировка`)
```
OLD: Click → Train selector with epochs
NEW: Shows warning:
  "Функция устарела. В NOWA обучение происходит ТОЛЬКО во время сна.
   Используйте 🌙 Сон!"
```

### ❌ Auto-training (`Авто-тренировка`)
```
Same deprecation warning
```

---

## Key Differences from Old GUI

### Old Way ❌
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

### New Way ✅
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

## Stats Display

### Before (Old)
```
Последнее действие: ...
Всего действий: ...
Средний вес: 0.123
```

### After (New)
```
Последнее действие: ...
Гиппокамп (шт): 5
Кортекс (шт): 2
Циклы сна: 3
```

---

## Memory Display

### Episodic Memory (Hippocampus)
```
Эпизодическая память:
  Опытов: 5
  Ср. подкр.: 1.2
```
Shows: Recent experiences with reinforcement count

### Semantic Memory (Cortex)
```
Семантическая память:
  Паттернов: 2
  Ср. сила: 0.85
```
Shows: Consolidated patterns created by sleep

---

## No More Weights!

### The Selector NOW
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

### The Selector THEN ❌
```python
selector.choose(context, learned_weights)
  ↓
selector.learn(action, reward)  ← Direct weight update
  ↓
Weights change immediately
```

---

## Loading Datasets

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

## Consolidation Process

During sleep, experiences are:

1. **Replayed** - Strengthened activation
2. **Clustered** - Similar experiences grouped
3. **Consolidated** - Clusters → semantic patterns
4. **Forgotten** - Unstable traces removed

Result: Cortical patterns that guide future behavior!

---

## Checking Progress

### Before Sleep
```
Click: Инспектор
→ Tab "Семантическая память"
→ See: 0 paттернов (empty)
```

### After Sleep
```
Click: Инспектор
→ Tab "Семантическая память"
→ See: 3+ паттерна (patterns created!)
→ Tab "Консолидация"
→ See: "Циклов сна: 1"
```

---

## Common Tasks

### Task 1: Load Training Data
```
1. Click: Загрузить датасет
2. Choose: JSON files
3. System: Loads to hippocampus
4. Status: Shows "✅ Loaded N experiences"
```

### Task 2: Train on Data (Sleep)
```
1. Click: 🌙 Сон
2. Set: 3 cycles
3. System: Consolidates experiences
4. Result: Patterns created
5. Status: Shows consolidation stats
```

### Task 3: Save State
```
1. Click: Сохранить
2. System: Saves hippocampus, cortex, selector
3. Status: Shows "✅ Состояние сохранено"
```

### Task 4: See Consolidation Details
```
1. Click: Инспектор
2. Tab 4: Консолидация
3. View: Sleep pipeline details
4. See: Consolidation ratio (patterns/experiences)
```

---

## Troubleshooting

### No Patterns Appearing
```
Q: Why are there 0 patterns in "Семантическая память"?
A: Patterns only appear after sleep consolidation!
   Click 🌙 Сон to create patterns.
```

### Behavior Not Changing
```
Q: Why does agent always choose the same action?
A: Need more sleep cycles to consolidate diverse patterns.
   Click 🌙 Сон → Set cycles: 5 or more
   Then try again.
```

### Experiences Not Storing
```
Q: Where did my feedback go?
A: Stored in hippocampus with intensity value.
   Check: Инспектор → "Эпизодическая память"
```

### Import Error
```
Q: "ModuleNotFoundError: No module named 'sleep'"
A: Make sure you're in src/ directory or have correct path
   python -m src.gui  (from project root)
```

---

## Remember

### Core Principle
> **Behavior is not learned. It emerges from experience and sleep.**

### Three Key Rules
1. **Waking** = Episodes + labile Q/Go/NoGo when reward is known
2. **Sleep** = Consolidate to patterns (ONLY learning)
3. **Selection** = Pressure-based (NO weights)

### The Proof
- Selector has NO `weights` attribute
- Selector has NO `learn()` method
- All learning in `SleepManager` (consolidation only)
- Patterns only appear after sleep
- Behavior emerges from consolidation

---

**NOWA GUI 2.0 - Cognitive Architecture Edition** ✅

# Спецификация пакета A — GenomeVector

English version: [SPEC_A_GenomeVector.en.md](SPEC_A_GenomeVector.en.md)

**Статус (27 сентября 2026 г.).** Документ ядра. Актуальное научное изложение комплекса на русском и английском языках приведено в [SCIENTIFIC_DESCRIPTION.ru.md](SCIENTIFIC_DESCRIPTION.ru.md). Текст ниже сохраняет формулировки исходной редакции: это нормативный контракт модуля либо лабораторная запись.

**Проект:** NOWA (расширение существующего)  
**Файл:** `src/genome.py`  
**Зависимости:** только стандартная библиотека Python (`math`, `random`, `dataclasses`, `typing`)  
**Версия спецификации:** 1.0

---

## 1. Назначение

`GenomeVector` — плоский вектор эволюционируемых параметров агента NOWA.  
Каждый ген соответствует конкретному параметру биологически мотивированного модуля.  
Геном не содержит логики поведения — только числовые параметры с ограничениями.

Геном используется для:
- инициализации агента через `AgentFactory` (пакет C)
- скрещивания и мутации при размножении (пакет E)
- ниширования при отборе (пакет F)

### Портреты колонии

Вкладка «Геном» инспектора колонии из четырёх поколений (зерно генератора 11). Кадр потомка перечисляет рекомбинированную линию. Кадр изменений генов — тот же агент, прокрученный к сдвигам от середины родителей. Галерея: [Эволюция в действии](../README.md#evolyutsiya-v-deystvii).

| Основатель `G0A4SM` | Потомок `G3A1SF` |
|---|---|
| ![Геном основателя](../Docs/media/ru/evolution-founder.png) | ![Геном потомка](../Docs/media/ru/evolution-descendant.png) |

![Изменения генов относительно середины родителей](../Docs/media/ru/evolution-mutations.png)

---

## 2. Структура данных

### 2.1 GeneDescriptor

```python
@dataclass
class GeneDescriptor:
    key: str           # уникальный идентификатор гена
    module: str        # модуль NOWA к которому относится
    min_val: float     # биологически обоснованный минимум
    max_val: float     # биологически обоснованный максимум
    default: float     # нейтральное значение (baseline организм)
    sigma: float       # типичный шаг мутации (стандартное отклонение)
    description: str   # описание биологического смысла
```

**Ограничения на GeneDescriptor:**
- `min_val < max_val` — обязательно
- `min_val <= default <= max_val` — обязательно
- `sigma > 0` — обязательно
- `sigma <= (max_val - min_val) / 2` — рекомендуется во избежание частого клампирования
- `key` уникален в пределах `GENE_REGISTRY`

### 2.2 GenomeVector

```python
@dataclass
class GenomeVector:
    genes: Dict[str, float]   # key -> значение
    generation: int = 0       # поколение (0 = первичная инициализация)
    lineage_id: str = ""      # идентификатор линии (для трекинга)
```

**Ограничения на GenomeVector:**
- `genes` содержит значения для **всех** ключей из `GENE_REGISTRY`
- каждое значение удовлетворяет `descriptor.min_val <= value <= descriptor.max_val`
- `generation >= 0`

---

## 3. Каталог генов (GENE_REGISTRY)

### Группа NM — нейромодуляторы

| ключ | модуль | min | max | default | sigma | описание |
|---|---|---|---|---|---|---|
| `nm_da_ne_weight` | neuromodulators | -0.4 | 0.0 | -0.2 | 0.05 | DA→NE ингибирование в матрице взаимодействий |
| `nm_ne_da_weight` | neuromodulators | 0.0 | 0.4 | 0.2 | 0.05 | NE→DA усиление |
| `nm_da_ach_weight` | neuromodulators | -0.5 | -0.1 | -0.3 | 0.05 | DA→ACh ингибирование |
| `nm_ach_da_weight` | neuromodulators | -0.5 | -0.1 | -0.3 | 0.05 | ACh→DA ингибирование |
| `nm_acc_k_ne` | neuromodulators | 0.2 | 1.0 | 0.5 | 0.10 | чувствительность ACC к норадреналину |
| `nm_acc_k_cort` | neuromodulators | 0.3 | 1.2 | 0.7 | 0.10 | чувствительность ACC к кортизолу |
| `nm_acc_k_ht` | neuromodulators | 0.1 | 0.6 | 0.35 | 0.05 | ингибирование конфликта серотонином |
| `nm_decay_half_life` | neuromodulators | 45.0 | 180.0 | 90.0 | 15.0 | период полураспада нейромодуляторов (сек) |

### Группа AF — аффективное пространство

| ключ | модуль | min | max | default | sigma | описание |
|---|---|---|---|---|---|---|
| `af_decay_valence` | affective_space | 0.80 | 0.98 | 0.92 | 0.03 | инерция настроения |
| `af_decay_arousal` | affective_space | 0.60 | 0.92 | 0.80 | 0.05 | скорость успокоения возбуждения |
| `af_decay_dominance` | affective_space | 0.88 | 0.99 | 0.97 | 0.02 | устойчивость ощущения контроля |
| `af_decay_stress` | affective_space | 0.55 | 0.88 | 0.75 | 0.05 | скорость снятия стресса |
| `af_decay_curiosity` | affective_space | 0.60 | 0.90 | 0.78 | 0.05 | угасание интереса без подкрепления |
| `af_decay_trust` | affective_space | 0.85 | 0.99 | 0.95 | 0.02 | инерция доверия |
| `af_decay_attachment` | affective_space | 0.85 | 0.99 | 0.93 | 0.02 | инерция привязанности |
| `af_lambda_reg` | affective_space | 0.01 | 0.10 | 0.05 | 0.01 | сила гомеостатического возврата |
| `af_baseline_adapt_rate` | affective_space | 0.0 | 0.01 | `1/(6×3600)` ≈ 4,63×10⁻⁵ | `0,5/(6×3600)` | скорость аллостатического baseline **за симулированную секунду** (τ ≈ 6 ч) |

### Группа WK — бодрствование и циркадный ритм

| ключ | модуль | min | max | default | sigma | описание |
|---|---|---|---|---|---|---|
| `wk_circadian_amplitude` | wakefulness | 0.1 | 0.5 | 0.3 | 0.05 | амплитуда суточного ритма |
| `wk_circadian_phase` | wakefulness | -1.57 | 1.57 | 0.0 | 0.30 | фазовый сдвиг (хронотип) |
| `wk_accumulation_factor` | wakefulness | 0.5 | 2.0 | 1.0 | 0.20 | множитель скорости накопления усталости |
| `wk_recovery_factor` | wakefulness | 0.5 | 2.0 | 1.0 | 0.20 | множитель скорости восстановления |

### Группа DR — drives (автономный организм)

| ключ | модуль | min | max | default | sigma | описание |
|---|---|---|---|---|---|---|
| `dr_curiosity_baseline` | autonomous | 0.05 | 0.40 | 0.18 | 0.05 | базовый уровень любопытства |
| `dr_social_drive_baseline` | autonomous | 0.05 | 0.45 | 0.22 | 0.05 | базовая социальная потребность |
| `dr_exploration_baseline` | autonomous | 0.05 | 0.35 | 0.12 | 0.04 | базовый уровень исследования |
| `dr_energy_recovery_rate` | autonomous | 0.02 | 0.10 | 0.05 | 0.01 | скорость восполнения энергии |
| `dr_cognitive_cost` | autonomous | 0.01 | 0.06 | 0.03 | 0.01 | энергетическая стоимость когниции |
| `dr_curiosity_threshold` | autonomous | 0.30 | 0.65 | 0.45 | 0.05 | порог активации любопытства |
| `dr_social_threshold` | autonomous | 0.35 | 0.70 | 0.50 | 0.05 | порог социальной активации |

### Группа LR — обучение и память

| ключ | модуль | min | max | default | sigma | описание |
|---|---|---|---|---|---|---|
| `lr_gamma` | value_layer | 0.80 | 0.99 | 0.95 | 0.02 | дисконт будущего вознаграждения |
| `lr_alpha_online` | value_layer | 0.01 | 0.08 | 0.03 | 0.01 | скорость онлайн обучения |
| `lr_tonic_slow_rate` | value_layer | 0.003 | 0.03 | 0.01 | 0.003 | инерция тонического дофамина |
| `lr_similarity_threshold` | hippocampus | 0.40 | 0.80 | 0.60 | 0.05 | порог сходства для активации памяти |
| `lr_consolidation_threshold` | sleep | 0.10 | 0.60 | 0.30 | 0.05 | минимальный порог консолидации |

### Группа IM — воображение

| ключ | модуль | min | max | default | sigma | описание |
|---|---|---|---|---|---|---|
| `im_goal_bias` | imagination | 0.10 | 0.70 | 0.35 | 0.08 | степень ориентированности воображения на цель |
| `im_confidence_decay` | imagination | 0.70 | 0.99 | 0.90 | 0.05 | затухание уверенности по глубине траектории |
| `im_novelty_weight` | imagination | 0.10 | 0.70 | 0.40 | 0.08 | вес новизны при оценке воображаемых траекторий |
| `im_value_blend` | imagination | 0.30 | 0.90 | 0.60 | 0.08 | баланс между памятью и воображением |

---

## 4. API класса GenomeVector

### 4.1 Инициализация

```python
@classmethod
def default(cls) -> "GenomeVector":
    """Создать геном с дефолтными значениями (нейтральный агент)."""

@classmethod
def random(cls, rng: random.Random = None) -> "GenomeVector":
    """
    Создать случайный геном.
    Каждый ген = равномерное распределение в [min_val, max_val].
    """

@classmethod
def from_dict(cls, data: dict) -> "GenomeVector":
    """
    Восстановить геном из словаря.
    Ключи не из GENE_REGISTRY игнорируются.
    Отсутствующие ключи заполняются default значениями.
    Значения вне диапазона клампируются с предупреждением.
    """
```

### 4.2 Мутация

```python
def mutate(
    self,
    rate: float = 0.05,
    sigma_scale: float = 1.0,
    rng: random.Random = None,
) -> "GenomeVector":
    """
    Создать мутировавшую копию генома.
    
    Алгоритм для каждого гена:
        1. Бросить монету с вероятностью rate
        2. Если мутация: value += N(0, descriptor.sigma * sigma_scale)
        3. Клампировать в [min_val, max_val]
    
    Аргументы:
        rate: вероятность мутации каждого гена [0.0, 1.0]
        sigma_scale: масштаб шума (1.0 = номинальный)
        rng: генератор случайных чисел (None = random.Random())
    
    Возвращает: новый GenomeVector (исходный не изменяется)
    
    Ограничения:
        - rate клампируется в [0.0, 1.0]
        - sigma_scale клампируется в [0.1, 5.0]
        - при rate=0.0 возвращается точная копия
        - при rate=1.0 мутируют все гены
    """
```

### 4.3 Скрещивание

```python
def crossover(
    self,
    other: "GenomeVector",
    alpha: float = 0.5,
    mode: str = "arithmetic",
    rng: random.Random = None,
) -> Tuple["GenomeVector", "GenomeVector"]:
    """
    Скрестить два генома, получить двух потомков.
    
    Режимы:
        "arithmetic":
            child_a[i] = alpha * self[i] + (1-alpha) * other[i]
            child_b[i] = (1-alpha) * self[i] + alpha * other[i]
            
        "uniform":
            для каждого гена независимо:
                child_a[i] = self[i] или other[i] с вероятностью 0.5
                child_b[i] = противоположный родитель
                
        "sbx" (simulated binary crossover, eta=2):
            сохраняет дисперсию популяции
            рекомендуется для числовых параметров
    
    Аргументы:
        other: второй родительский геном
        alpha: вес первого родителя для "arithmetic" [0.0, 1.0]
        mode: "arithmetic" | "uniform" | "sbx"
        rng: генератор случайных чисел
    
    Возвращает: кортеж (child_a, child_b)
    
    Ограничения:
        - alpha клампируется в [0.0, 1.0]
        - неизвестный mode вызывает ValueError
        - generation потомков = max(self.generation, other.generation) + 1
        - все значения потомков клампируются в допустимые диапазоны
    """
```

### 4.4 Расстояние и сходство

```python
def distance(self, other: "GenomeVector") -> float:
    """
    Нормированное евклидово расстояние в пространстве генов.
    
    Нормировка: каждый ген масштабируется в [0, 1] перед вычислением.
        scaled[i] = (value[i] - min_val[i]) / (max_val[i] - min_val[i])
    
    Расстояние = sqrt(sum((scaled_a[i] - scaled_b[i])^2)) / sqrt(N)
    
    Диапазон результата: [0.0, 1.0]
    0.0 = идентичные геномы
    1.0 = максимально различные геномы
    """

def similarity(self, other: "GenomeVector") -> float:
    """Возвращает 1.0 - distance(other)."""
```

### 4.5 Развёртка в параметры модулей

```python
def to_agent_params(self) -> dict:
    """
    Развернуть геном в словарь параметров для AgentFactory.
    
    Возвращает структуру:
    {
        "affective_space": {
            "axis_decay": {
                "valence": genes["af_decay_valence"],
                "arousal": genes["af_decay_arousal"],
                ...
            },
            "lambda_reg": genes["af_lambda_reg"],
            "baseline_adapt_rate": genes["af_baseline_adapt_rate"],
        },
        "wakefulness": {
            "circadian_amplitude": genes["wk_circadian_amplitude"],
            "circadian_phase": genes["wk_circadian_phase"],
            "accumulation_rate_factor": genes["wk_accumulation_factor"],
            "recovery_rate_factor": genes["wk_recovery_factor"],
        },
        "neuromodulators": {
            "interaction_overrides": {
                "da_ne": genes["nm_da_ne_weight"],
                "ne_da": genes["nm_ne_da_weight"],
                "da_ach": genes["nm_da_ach_weight"],
                "ach_da": genes["nm_ach_da_weight"],
            },
            "acc_k_ne": genes["nm_acc_k_ne"],
            "acc_k_cort": genes["nm_acc_k_cort"],
            "acc_k_ht": genes["nm_acc_k_ht"],
            "decay_half_life": genes["nm_decay_half_life"],
        },
        "autonomous": {
            "drive_baselines": {
                "curiosity": genes["dr_curiosity_baseline"],
                "social_drive": genes["dr_social_drive_baseline"],
                "exploration": genes["dr_exploration_baseline"],
            },
            "drive_thresholds": {
                "curiosity": genes["dr_curiosity_threshold"],
                "social_drive": genes["dr_social_threshold"],
            },
            "energy_recovery_rate": genes["dr_energy_recovery_rate"],
            "cognitive_cost": genes["dr_cognitive_cost"],
        },
        "value_layer": {
            "gamma_default": genes["lr_gamma"],
            "alpha_online_default": genes["lr_alpha_online"],
            "tonic_slow_rate": genes["lr_tonic_slow_rate"],
        },
        "hippocampus": {
            "similarity_threshold": genes["lr_similarity_threshold"],
        },
        "sleep": {
            "consolidation_threshold": genes["lr_consolidation_threshold"],
        },
        "imagination": {
            "goal_bias": genes["im_goal_bias"],
            "confidence_decay": genes["im_confidence_decay"],
            "state_novelty_weight": genes["im_novelty_weight"],
            "value_blend": genes["im_value_blend"],
        },
    }
    """
```

### 4.6 Сериализация

```python
def to_dict(self) -> dict:
    """
    Сериализовать в словарь.
    Возвращает:
    {
        "version": "1.0",
        "generation": int,
        "lineage_id": str,
        "genes": {key: value, ...}
    }
    """

def to_array(self) -> List[float]:
    """
    Вернуть значения генов как список в детерминированном порядке.
    Порядок = порядок объявления в GENE_REGISTRY.
    Используется для математических операций (numpy совместим).
    """

@classmethod
def from_array(cls, array: List[float], generation: int = 0) -> "GenomeVector":
    """
    Восстановить геном из списка.
    Порядок должен совпадать с to_array().
    Значения клампируются в допустимые диапазоны.
    Raises ValueError если len(array) != len(GENE_REGISTRY).
    """
```

### 4.7 Диагностика

```python
def validate(self) -> List[str]:
    """
    Проверить корректность генома.
    Возвращает список строк с предупреждениями (пустой = всё ок).
    Проверяет: диапазоны, NaN, Inf.
    """

def summary(self) -> dict:
    """
    Краткая статистика по группам генов.
    {
        "NM": {"mean": float, "std": float, "deviation_from_default": float},
        "AF": {...},
        ...
    }
    """
```

---

## 5. Что НЕ входит в геном

Следующие параметры намеренно исключены и одинаковы для всех агентов:

- Набор доступных действий — определяется средой
- Размер гиппокампа — одинаков для честного сравнения
- Знаки в матрице взаимодействий нейромодуляторов — меняются только веса, не топология
- Структура сети модулей — архитектура фиксирована
- Параметры SWS/REM разделения сна — sleep mechanics одинаковы

---

## 6. Ограничения реализации

1. `GenomeVector` — **неизменяемый** после создания. `mutate()` и `crossover()` возвращают новые объекты.
2. Никаких зависимостей кроме стандартной библиотеки Python.
3. Все операции детерминированы при фиксированном `rng`.
4. `to_dict()` / `from_dict()` — полный round-trip без потерь.
5. `from_dict()` с неполным словарём заполняет отсутствующие гены из `default` (обратная совместимость).
6. Файл `genome.py` не импортирует ни один модуль NOWA — нулевые циклические зависимости.

---

## 7. Тест-кейсы

### TC-01: Создание дефолтного генома

```python
genome = GenomeVector.default()

# Все гены присутствуют
assert set(genome.genes.keys()) == set(GENE_REGISTRY.keys())

# Значения равны default
for key, desc in GENE_REGISTRY.items():
    assert genome.genes[key] == desc.default, f"TC-01 fail: {key}"

# Валидация чистая
assert genome.validate() == []

# generation = 0
assert genome.generation == 0
```

### TC-02: Мутация не изменяет оригинал

```python
original = GenomeVector.default()
mutated = original.mutate(rate=1.0, sigma_scale=2.0, rng=random.Random(42))

# Оригинал не изменён
for key in GENE_REGISTRY:
    assert original.genes[key] == GENE_REGISTRY[key].default

# Мутированный отличается
assert original.genes != mutated.genes

# Все значения в диапазоне
for key, desc in GENE_REGISTRY.items():
    assert desc.min_val <= mutated.genes[key] <= desc.max_val, f"TC-02 range fail: {key}"
```

### TC-03: Мутация rate=0 — точная копия

```python
genome = GenomeVector.default()
copy = genome.mutate(rate=0.0, rng=random.Random(0))
assert genome.genes == copy.genes
```

### TC-04: Скрещивание arithmetic

```python
rng = random.Random(0)
a = GenomeVector.random(rng)
b = GenomeVector.random(rng)

child_a, child_b = a.crossover(b, alpha=0.5, mode="arithmetic")

# Потомки между родителями
for key in GENE_REGISTRY:
    val_a = a.genes[key]
    val_b = b.genes[key]
    lo, hi = min(val_a, val_b), max(val_a, val_b)
    # При alpha=0.5 оба потомка должны быть средним
    assert abs(child_a.genes[key] - (0.5 * val_a + 0.5 * val_b)) < 1e-9

# generation = max(0, 0) + 1 = 1
assert child_a.generation == 1
assert child_b.generation == 1
```

### TC-05: Скрещивание uniform — каждый ген от одного родителя

```python
rng = random.Random(42)
a = GenomeVector.default()
b = GenomeVector.random(rng)
child_a, child_b = a.crossover(b, mode="uniform", rng=random.Random(42))

for key in GENE_REGISTRY:
    # Каждый ген потомка точно равен одному из родителей
    val = child_a.genes[key]
    assert val == a.genes[key] or val == b.genes[key], f"TC-05 fail: {key}"
    # child_b берёт противоположный
    other_val = child_b.genes[key]
    if val == a.genes[key]:
        assert other_val == b.genes[key]
    else:
        assert other_val == a.genes[key]
```

### TC-06: Расстояние

```python
a = GenomeVector.default()
b = GenomeVector.default()

# Расстояние до себя = 0
assert a.distance(a) == 0.0
assert a.distance(b) == 0.0

# Симметрия
c = GenomeVector.random(random.Random(7))
assert abs(a.distance(c) - c.distance(a)) < 1e-9

# Диапазон [0, 1]
assert 0.0 <= a.distance(c) <= 1.0

# Максимальное расстояние при полярных геномах
min_genome = GenomeVector(genes={k: d.min_val for k, d in GENE_REGISTRY.items()})
max_genome = GenomeVector(genes={k: d.max_val for k, d in GENE_REGISTRY.items()})
assert abs(min_genome.distance(max_genome) - 1.0) < 1e-9
```

### TC-07: Сериализация round-trip

```python
rng = random.Random(13)
genome = GenomeVector.random(rng)
genome_dict = genome.to_dict()
restored = GenomeVector.from_dict(genome_dict)

assert genome.genes == restored.genes
assert genome.generation == restored.generation
assert genome.lineage_id == restored.lineage_id
```

### TC-08: to_array / from_array round-trip

```python
genome = GenomeVector.random(random.Random(99))
array = genome.to_array()

assert len(array) == len(GENE_REGISTRY)

restored = GenomeVector.from_array(array)
assert genome.genes == restored.genes
```

### TC-09: from_array с неверной длиной

```python
try:
    GenomeVector.from_array([0.1, 0.2])  # слишком короткий
    assert False, "должен вызвать ValueError"
except ValueError:
    pass
```

### TC-10: to_agent_params содержит все ключи

```python
genome = GenomeVector.default()
params = genome.to_agent_params()

# Все ожидаемые модули присутствуют
required_modules = [
    "affective_space", "wakefulness", "neuromodulators",
    "autonomous", "value_layer", "hippocampus", "sleep", "imagination"
]
for module in required_modules:
    assert module in params, f"TC-10: отсутствует модуль {module}"

# Значения соответствуют генам
assert params["affective_space"]["axis_decay"]["valence"] == genome.genes["af_decay_valence"]
assert params["value_layer"]["gamma_default"] == genome.genes["lr_gamma"]
assert params["wakefulness"]["circadian_amplitude"] == genome.genes["wk_circadian_amplitude"]
```

### TC-11: validate обнаруживает нарушения

```python
genome = GenomeVector.default()
genome.genes["lr_gamma"] = 1.5  # вне диапазона

warnings = genome.validate()
assert len(warnings) > 0
assert any("lr_gamma" in w for w in warnings)
```

### TC-12: crossover с неизвестным mode

```python
a = GenomeVector.default()
b = GenomeVector.default()
try:
    a.crossover(b, mode="unknown_mode")
    assert False, "должен вызвать ValueError"
except ValueError:
    pass
```

### TC-13: Детерминизм при фиксированном rng

```python
genome = GenomeVector.default()
m1 = genome.mutate(rate=0.3, rng=random.Random(42))
m2 = genome.mutate(rate=0.3, rng=random.Random(42))
assert m1.genes == m2.genes
```

### TC-14: summary содержит все группы

```python
genome = GenomeVector.default()
s = genome.summary()

for group in ["NM", "AF", "WK", "DR", "LR", "IM"]:
    assert group in s
    assert "mean" in s[group]
    assert "std" in s[group]
    assert "deviation_from_default" in s[group]
```

---

## 8. Примечания для реализующего агента

- `GENE_REGISTRY` реализовать как `OrderedDict` или список для детерминированного порядка в `to_array()`
- SBX crossover: использовать eta=2 (стандартное значение для непрерывных параметров)
- `lineage_id` при создании через `default()` или `random()` = пустая строка; при `crossover()` = `f"{parent_a.lineage_id}x{parent_b.lineage_id}"` (обрезать до 64 символов)
- Все методы должны быть чистыми функциями без побочных эффектов кроме явно указанного (`rng` модифицируется)
- Python версия: 3.10+, никакого numpy в обязательных зависимостях (опционально для `to_array`)

# Issue #27 — Менделевское наследование в колонии: спецификация реализации

Закрывает #27. PR #64. Связано: [issue-24-silent-failures.ru.md](issue-24-silent-failures.ru.md) (снимок отца при зачатии). Коммиты реализации: `ba77db9`, `71c872d`.

English: [issue-27-inheritance.en.md](issue-27-inheritance.en.md)

Область: демо **Colony chinchillas** (`Demo/Colony chinchillas/`). Дефолт **swarm** в репозитории остаётся `arithmetic` (`src/swarm.py`); при рождении шиншилл — только `uniform`.

---

## 1. Проблема

Прежний `_inherit_nowa_from` смешивал менделевский кроссовер генома со смешанным фенотипическим наследованием:

| Симптом | Причина |
| --- | --- |
| Сиблинги почти одинаковы; дисперсия популяции схлопывается | `GenomeVector.crossover(..., alpha=0.5, mode="arithmetic")` усреднял аллели → ребёнок в середине родителей до мутации. |
| Острая стресс-физиология родителя у детёныша | Текущие уровни нейромодуляторов (напр. кортизол) усреднялись с шумом. |
| Наследование `axis_decay` / `social_drive` «мёртвое» | Значения усреднялись, затем перезаписывались в `AgentFactory._apply_genome_to_agent` из генома (`af_decay_*`, `dr_social_drive_baseline`). |
| Энергия не аллель | `inherit_scalar` усреднял **текущие** балансы родителей. |

---

## 2. Решение и биологическое обоснование

**Решение (согласовано с владельцем):** максимальная биологичность — генотип через менделевское наследование целого гена; неонатальная физиология из дефолтов генома и конструктора, не из моментального состояния родителей.

| Механизм | Поведение |
| --- | --- |
| **Кроссовер генома** | `mode="uniform"`: каждый ген целиком от матери или отца (правило `random() >= 0.5` в `GenomeVector.crossover`), затем `mutate(rate=0.05)` без изменений. |
| **Нейромодуляторы** | Не наследуются; у детёныша baselines конструктора (напр. `NeuromodulatorState.BASELINE_CORT` ≈ `0.05`). |
| **`axis_decay`, `social_drive`** | Только из генома → `AgentFactory._apply_genome_to_agent`; циклы усреднения удалены. |
| **Энергия** | Константа `NEWBORN_ENERGY = 1.0` (отдохнувший неонат; метаболическое состояние ≠ аллель). |
| **Без генома** | Без изменений: warning, `genome is None`, свежие baselines (issue #24). |

Эволюция swarm в `src/swarm.py` по умолчанию **arithmetic**; рождение в колонии — только **uniform**.

---

## 3. Изменения по файлам

| Файл | Изменение |
| --- | --- |
| `Demo/Colony chinchillas/src/colony_agent.py` | `NEWBORN_ENERGY`; `_inherit_nowa_from`: uniform, `pre_genes` для meta, удалено усреднение NM/affect/social/energy; обновлён `genome_inheritance_meta`; `self.energy = NEWBORN_ENERGY`. |
| `Demo/Colony chinchillas/src/colony_reproduction_helpers.py` | Удалён `inherit_scalar`. |
| `.github/workflows/tests.yml` | `push` только на `main`; `concurrency` `tests-${{ github.ref }}`, `cancel-in-progress: true` (отменяет устаревшие прогоны на том же ref). Двойной прогон push ветки + PR убирает `push.branches: [main]`, а не общая concurrency-группа. |
| `Demo/Colony chinchillas/tests/test_issue27_inheritance.py` | Новый приёмочный набор для #27. |
| `Demo/Colony chinchillas/tests/test_issue24_silent_failures.py` | Ожидания под uniform (фиксация RNG на аллели отца). |
| `Demo/Colony chinchillas/tests/test_nowa_agent.py` | `test_tc07_*`: новорождённый **не** копирует уровни NM родителей. |

---

## 4. Поля `genome_inheritance_meta`

| Поле | Заметка |
| --- | --- |
| `crossover_mode` | `"uniform"` (было `"arithmetic"`). |
| `crossover_alpha` | **Удалено** (нигде не читалось). |
| `mother_contrib_mean` / `father_contrib_mean` | Доля гетерозиготных локусов, где аллель ребёнка совпала с матерью / отцом **до мутации** (`pre_genes` vs гены родителей). |
| `top_shifted_genes[].midpoint_shift` | `child_val − (m_val + f_val)/2`; по-прежнему информативно, но чаще подсвечивает локусы, где родители **различались** (ребёнок — конечная точка, не blend). |

Остальные ключи (`mode`, `mutation_rate`, `gene_count`, lineage, id родителей) без изменений.

---

## 5. Совместимость

| Область | Влияние |
| --- | --- |
| Save/load | С #65 ([issue-65-save-genome.ru.md](issue-65-save-genome.ru.md)) `ColonyStorage` сохраняет и восстанавливает `genome_inheritance_meta` (после #27: `crossover_mode` = `"uniform"`, без `crossover_alpha`). В файлах до #65 ключа нет; при загрузке — `{}`. В сохранении может остаться legacy `crossover_alpha`, если агент родился до #27 и был сохранён после #65. |
| Снимок зачатия (#24) | По-прежнему для генома отца при его смерти; меняется только режим кроссовера. |
| Ядро `src/` | Без изменений. Дефолт swarm `crossover_mode` — `arithmetic`. |
| API | Алиас `_inherit_from` без изменений; `inherit_scalar` убран из helpers (только колония). |

---

## 6. Тесты и критерии приёмки

**Основной:** `Demo/Colony chinchillas/tests/test_issue27_inheritance.py`

- Сиблинги различаются; каждый ген (до мутации) = аллель матери **или** отца; в meta `crossover_mode == "uniform"`, нет `crossover_alpha`.
- Симуляция разведения: дисперсия при uniform не схлопывается как при arithmetic (`uniform > arithmetic × 5` за 8 поколений).
- Высокий кортизол матери / energy / `social_drive` родителей не копируются; energy ребёнка `1.0`; `social_drive` и `axis_decay["stress"]` из генов генома.
- Рождение без генома: warning сохранён, baselines + `NEWBORN_ENERGY`.

**Обновлены:** `test_issue24_silent_failures.py`, `test_nowa_agent.py` (см. §3).

**CI:** workflow green на PR #64 (job pytest).

**Критерии приёмки:**

1. Рождение в колонии: кроссовер `uniform` + мутация `rate=0.05`.
2. Неонатальные уровни нейромодуляторов — baselines, не среднее родителей.
3. `social_drive` и affective `axis_decay` только из применения генома.
4. У новорождённого `energy == NEWBORN_ENERGY` (`1.0`).
5. Генетическая дисперсия при uniform существенно выше схлопывания arithmetic (регрессионный тест).
6. Путь без генома по-прежнему пишет warning и не падает молча.

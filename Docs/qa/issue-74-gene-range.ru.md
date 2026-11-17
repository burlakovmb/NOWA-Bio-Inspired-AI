# QA issue #74 — диапазон `af_baseline_adapt_rate`

Ветка: `team/issue-74-gene-range`. HEAD на момент прогона: `79cee90`. PR: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/81
English: [issue-74-gene-range.en.md](issue-74-gene-range.en.md).

Код продукта в этом проходе не менялся. Новый PR не создавался, мержа не было. CI не ждали. Полный pytest не запускался.

Машина: Python 3.12.3, pytest 9.2.0. Пробы с `PYTHONPATH=src`.

## Вердикт

**PASS** (`79cee90`).

`af_baseline_adapt_rate` = [1/86400, 1/5400], default 1/21600 равен `affective_space.DEFAULT_BASELINE_ADAPT_RATE`. `GeneDescriptor` валиден. random, mutate (включая `sigma_scale` выше потолка 5) и crossover `arithmetic` / `uniform` / `sbx` держат τ в 1,5–24 ч. Legacy 0.002 через `GenomeVector.from_dict` и через `AgentStorage.load_agent` (`.nowa`) зажимается до max: одно `RuntimeWarning`, без падения. Значение внутри диапазона грузится без предупреждения. Отсутствующее поле даёт default, тоже без предупреждения. `storage` импортирует `GENE_REGISTRY` напрямую, цикл с `genome` не возникает. `AffectiveSpace.__post_init__` по-прежнему жмёт [0, 0.2]. Смена 0.015 → `1/(3*3600)` в `test_affective_space_save_load` обоснована. 300 с `Agent.step` без стрессоров: baseline стресса на уставке.

## Покрытие

| # | Проверка | Результат |
| --- | --- | --- |
| 1 | Диапазон, default, `GeneDescriptor` | Pass. min `1.1574074074074073e-05`, max `0.00018518518518518518`, default `4.6296296296296294e-05` == `DEFAULT_BASELINE_ADAPT_RATE`. min < default < max, sigma > 0 |
| 2 | random / mutate / crossover и τ | Pass. Тест: 1000 random, 200 mutate при scale 5 и 1, режимы `sbx` и `arithmetic`. Проба QA: те же операторы плюс `uniform` и `sigma_scale=100`, 300 итераций, нарушений 0 |
| 3 | Legacy 0.002, fallback, in-range, импорт | Pass. `from_dict` и `load_agent`: 1 `RuntimeWarning`, значение = max. `1/(3*3600)` → `9.259259259259259e-05` и max: 0 предупреждений. Ключ удалён из `.nowa`: default, 0 предупреждений. Совместный import прошёл; `genome.py` — только stdlib |
| 4 | clamp [0, 0.2] и смена теста | Pass. `affective_space.py` вне diff. Проба: 0.5 → 0.2, −0.1 → 0.0. 0.015 выше нового max, равенство roundtrip сломалось бы; `1/(3*3600)` внутри и гена, и [0, 0.2]. Тест legacy по-прежнему видит в файле 0.002 и max после load |
| 5 | 300 с, dt 0.25, живой агент | Pass. `AgentFactory.spawn_random`, seed 74, 1200× `Agent.step([], reward=0, novelty=0, conflict=0, intensity=0, dt=0.25)`. rate `3.3656613124657915e-05` внутри диапазона. baseline = setpoint = 0, max \|Δ\| = 0, ось stress = 0. Прогон дешёвый (20 шагов 0.023 с, оценка 1200 шагов 1.4 с) |
| 6 | `Demo/` и `Docs/` | Pass. `git diff --stat origin/main...HEAD`: `src/genome.py`, `src/storage.py`, `tests/test_affective_space_storage.py`, `tests/test_affective_time.py`, `tests/test_genome_vector.py` |
| 7 | Целевые тесты и grep Demo | Pass. 62 passed, 26.09s, exit 0. В `Demo/**/tests` совпадений `_deserialize_genome` и `_genome_from_plain` нет, дополнительные файлы не запускались. Оба хелпера в исходниках зовут `GenomeVector.from_dict` |

```
python3 -m pytest -q --no-header -p no:warnings tests/test_genome_vector.py tests/test_agent_factory.py tests/test_affective_time.py tests/test_affective_space_storage.py tests/test_affective_core_phase4.py | tail -n 30
```

`62 passed in 26.09s`

## Дефекты

Нет.

## Рекомендации

- Тест кроссовера чередует `sbx` и `arithmetic` и не вызывает `uniform`. Зажим стоит после выбора режима; проба нарушений не показала.
- `test_fed_space_at_max_adapt_rate_keeps_stress_baseline_near_setpoint` стартует из равновесия (разрыв 0). Для прогона без стрессоров этого хватает: живой агент дал тот же нуль.

## Готовность

Чеклист закрыт, к ревью готово. CI на PR #81 не смотрели.

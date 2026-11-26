# QA issue #76 задача 1 — вариант A, пол стоимости не ниже δ

Ветка: `team/vc76-fair-1b`. Проверяемый коммит: `01bd07460cf67dd39c28fbaff21e2a43d4dee785` (`fix(issue-76): keep the stage 1b cost floor at least delta`). Родитель: `b35676a`. PR: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/91. Issue: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/76.
English: [issue-76-task1-optionA-qa.en.md](issue-76-task1-optionA-qa.en.md).

Объём — только этот коммит (вариант A). Родительский коммит, который ввёл `cost_vs_chance`, вне проверки. Длинных прогонов по сидам нет. Код продукта не менялся.

Машина: Linux, Python 3.12.3, pytest 9.2.0. Тесты демо добавляют `Demo/Virtual company/src` и `src/` репозитория через `Demo/Virtual company/tests/conftest.py`.

## Вердикт

**PASS.**

Гард стоимости Stage 1b — это `max(min(0.9*median, median-IQR), δ)`, где δ = `stage_baseline.cost_vs_chance_floor_delta`, по умолчанию 0.03, зажим 0.02–0.05. Случайный уровень `cost_vs_chance` = 0 не проходит околонулевой или отрицательный baseline. Когда и `0.9*median`, и `median-IQR` выше δ, пол остаётся на прежнем статистическом значении. У остальных критериев прежний пол. `src/` не затронут. Указанные тесты проходят.

## Покрытие

| # | Проверка | Результат |
| --- | --- | --- |
| 1 | Формула в `stage_baseline.non_regression_floor` и применение в `ProcurementFitnessEvaluator.check_non_regression` | Pass. `base_multiplier` — это `NON_REGRESSION_FLOOR` (0.9). `lower_bound` — зажатый δ. Отображение `nr_floors_from_baseline` вызывает ту же функцию |
| 2 | Границы: median < 0, IQR = 0, IQR > median, пустой baseline | Pass, таблица 1. Гард и показанный пол совпали на каждой строке. Сырой критерий по-прежнему обрезается на 0: `non_regression_floor(0.1, 0.5)` равен 0.0, пол stockout при median 0.9 / IQR 0 остался 0.81 |
| 3 | δ из YAML, отсутствие ключа, значения вне диапазона, нечисловые; старый baseline и чекпоинт без δ | Pass, таблица 2. В `configs/default_world.yaml` стоит 0.03. `SandboxConfig.load(None)` даёт 0.03 |
| 4 | `run_sandbox.py`, `gui_controller.py`, `gui_app.py`, `quarter_diagnostics.py`, `sandbox_config.py` | Pass. Дифф — проброс δ и показ пола стоимости. Resume, посев, перенос поставщиков и остальные секции конфига не изменены. Круговой путь `default_world.yaml` через `to_dict` / `from_mapping` совпадает |
| 5 | `src/` и захардкоженные предпочтения агента | Pass. `git diff main...HEAD -- src/` и `git diff 01bd074^..01bd074 -- src/` пусты. `git diff 01bd074^..01bd074 -G 'preference\|intuition\|prior\|bias\|reward'` пуст. `seed_intuition` в диффе нет |
| 6 | Тесты: random при baseline ≈ 0 не проходит; оба выражения > δ — прежнее поведение; δ из конфига | Pass. Имена ниже. Весь целевой прогон: 176 passed, 1 skipped, 1.64s |

Таблица 1 — пробник `non_regression_floor(..., lower_bound=0.03)` против `max(min(0.9*median, median-IQR), 0.03)`. Отрицательный IQR перед формулой зажимается в 0, как в загрузчике. `cost_vs_chance = 0` — уровень случайного выбора. `passes` — это `check_non_regression` для `cost_efficiency`.

| Case | median | IQR | statistical | floor | 0 passes |
| --- | --- | --- | --- | --- | --- |
| median < 0 | -0.08 | 0.02 | -0.10 | 0.03 | no |
| median < 0, IQR = 0 | -0.08 | 0 | -0.08 | 0.03 | no |
| IQR = 0, high median | 0.40 | 0 | 0.36 | 0.36 | no |
| IQR = 0, near zero | 0.02 | 0 | 0.018 | 0.03 | no |
| IQR > median | 0.10 | 0.25 | -0.15 | 0.03 | no |
| IQR > median, high median | 0.50 | 0.60 | -0.10 | 0.03 | no |
| both terms > δ | 0.40 | 0.05 | 0.35 | 0.35 | no |
| both zero | 0 | 0 | 0 | 0.03 | no |
| baseline ≈ 0 | 0.001 | 0.004 | -0.003 | 0.03 | no |

На строке «both terms > δ» значение `cost_vs_chance` на 0.01 ниже 0.35 не проходит, на 0.01 выше проходит. `budget_discipline` и `stockout_avoidance` остаются пройденными. Поднятие δ до 0.04 эту границу не сдвигает: 0.35 > 0.04. При median 0 и IQR 0 значение `cost_vs_chance` 0.035 проходит при δ 0.02 и не проходит при δ 0.05: гард берёт δ из конфига.

Пустой baseline:

- `compute_stage_1a_baseline([])` бросает `ValueError`.
- `check_non_regression` на `{}` помечает все четыре критерия Stage 1a как пройденные (нет данных, δ не применяется). `nr_floors_from_baseline({})` возвращает `{}`.
- 15 кварталов без `cost_vs_chance` не получают `cost_vs_chance_median` и `cost_vs_chance_iqr`. Остаётся сырая проверка: cost 0.5 против baseline 0.8 не проходит (`0.5 < 0.8*0.9`), cost 0.9 проходит. δ не применяется.
- Файл baseline `{}` даёт `ValueError`. Голая карта критериев читается и не содержит нормированных ключей.

Таблица 2 — `SandboxConfig.from_mapping` / YAML.

| Input | δ |
| --- | --- |
| нет секции `stage_baseline`, нет ключа, null, `abc`, `''`, `.nan`, `.inf`, `[0.04]` | 0.03 |
| 0.01 | 0.02 |
| 0.2 | 0.05 |
| 0.02, 0.05, 0.04, `'0.04'` | 0.02, 0.05, 0.04, 0.04 |
| поставленный `default_world.yaml`, `SandboxConfig.load(None)` | 0.03 |

`ProcurementFitnessEvaluator(cost_vs_chance_floor_delta=...)` зажимает так же: 0.01 → 0.02, 0.9 → 0.05, `"nope"` → 0.03, `None` → 0.03.

Старые файлы: JSON baseline с `cost_vs_chance_median` / `cost_vs_chance_iqr` и без ключа δ читает оба числа и не придумывает поле δ. Чекпоинт, записанный через `dump_state` (`format` `nowa-sandbox-checkpoint`, схема 2) без ключа δ, читается: `last_quarter` 2, `world_summary.cost_vs_chance` 0.01, fitness 0.4. δ при resume берётся из текущего конфига, не из чекпоинта.

`gui_app.SandboxLabApp._refresh_nr_floors` (без окна): baseline с median 0 и IQR 0.05 и YAML δ 0.04 показывает пол стоимости 0.04 и пол stockout 0.81. Пустой путь конфига показывает 0.03. Отсутствующий путь baseline оставляет `controller.last_nr_floors`.

Тесты, которые закрывают три обязательных случая:

- `TestNormalizedCostGuard.test_random_policy_fails_near_zero_baseline_because_of_delta` — median 0, IQR 0.05, `cost_vs_chance` 0 не проходит; stockout проходит.
- `TestNormalizedCostGuard.test_floor_matches_previous_formula_when_both_terms_exceed_delta` и `TestNormalizedSavingsBaseline.test_floor_unchanged_when_both_terms_exceed_delta` — median 0.40, IQR 0.05, пол `min(0.36, 0.35)`.
- `TestCostVsChanceFloorDelta.test_delta_is_read_from_config` — поставленные 0.03, YAML 0.04 сохраняется в оценщике, 0.01 зажимается в 0.02, 0.2 зажимается в 0.05.
- `test_old_baseline_file_loads_and_keeps_the_raw_cost_guard` — файл baseline до нормированных полей, сырая проверка стоимости.

```
python3 -m pytest -q --no-header -rs -p no:warnings \
  "Demo/Virtual company/tests/test_baseline_methodology.py" \
  "Demo/Virtual company/tests/test_graduation_non_regression.py" \
  "Demo/Virtual company/tests/test_sandbox_config.py" \
  "Demo/Virtual company/tests/test_stage_baseline.py" \
  "Demo/Virtual company/tests/test_stage_baseline_strictness.py" \
  "Demo/Virtual company/tests/test_procurement_fitness.py" \
  "Demo/Virtual company/tests/test_gui_controller.py" \
  "Demo/Virtual company/tests/test_run_sandbox.py"
```

`176 passed, 1 skipped in 1.64s`. Пропуск: `test_gui_controller.py::TestFitnessChartSmoke::test_set_data_and_clear` — Tk/Tcl здесь недоступен. Остальные тесты `test_gui_controller` и `test_run_sandbox` прошли, включая resume из чекпоинта.

## Дефекты

Нет.

## Рекомендации

- Юнит-тесты не фиксируют median < 0, IQR = 0, IQR > median, пустой baseline, отсутствующий ключ YAML и нечисловое значение. Это закрыл пробник выше. Следующая правка может убрать один из этих случаев без красного теста.
- `test_delta_is_read_from_config` проверяет сохранённое поле. Он не показывает, что 0.035 проходит при δ 0.02 и не проходит при δ 0.05. Это показал пробник.
- YAML `true` / `yes` становится 0.05, а не 0.03. PyYAML читает их как boolean, `float(True)` равен 1.0, и зажим поднимает значение к верхней границе диапазона. Строки, null, NaN и inf падают в 0.03. Результат остаётся внутри 0.02–0.05 и делает пол строже, поэтому политика уровня случайного выбора всё равно не проходит.
- Если файл baseline читается, а файл конфига нет, `_refresh_nr_floors` показывает δ 0.03 вместо `controller.last_nr_floors`. Путь обучения этот refresh не использует: он берёт уже загруженный для прогона объект конфига.

# QA issue #54 — аффект в симулированных секундах (ядро)

Ветка: `team/issue-54-core-affect-time`. Код под проверкой: `80b7054` (следующий `bb748a1` — только документация). PR: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/72. Issue: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/54.

Код продукта не менялся. Полный pytest локально не гонялся. CI на `80b7054` принят как зелёный (2185 тестов), повторно не проверялся. Машина: Python 3.12.3, pytest 9.2.0.

## Вердикт

**PASS**

Восемь пунктов чеклиста части 1 проходят. Оси и baseline при нулевых импульсах совпадают на 1 с и 10 с (и на 0.25 с / 2.5 с) с запасом относительно 1e-9. Есть одна граница: `decision_only` с `dt=0` на commit продвигает A(t) на 1 с.

## Покрытие (8 пройдено / 0 провалено / 0 не запускалось)

| # | Проверка | Результат |
| --- | --- | --- |
| 1 | 30 с стресса, импульс 1.0/с | Pass. `test_sustained_stress_does_not_drag_baseline_within_30s`. Проба: ось stress `1.0`, baseline `0.00139`, b0 `0` (не ~0.96) |
| 2 | 48 ч без стрессора | Pass. `test_baseline_returns_toward_setpoint_without_stressors`. Проба: stress `0.7 → 0.0948`, valence `-0.4 → 0.0323` к b0 `0.1`. b0 не изменился |
| 3 | 3 с сон и бодрствование | Pass. `test_sleep_relaxes_faster_than_wake_for_the_same_time`. Проба: ось `0.636 → 0.536`, baseline `0.549 → 0.519`, оба ближе к 0. `SLEEP_RECOVERY_SCALE=4`, возврат `0.25` |
| 4 | 20×1 с и 2×10 с, импульсов нет, `legacy_compat_weight=0` | Pass. `test_one_second_steps_match_ten_second_steps`. Макс. расхождение осей `7.8e-16`, baseline `9.2e-16`. Дополнительно 10×0.25 с и 1×2.5 с: `< 4e-16` |
| 5 | `decision_only` + recall, затем commit | Pass для положительного host dt. Тест на `dt=1`: один вызов `0.0` и один `1.0`. Проба: `dt=2.5 → [0.0, 2.5]`, `dt=0.25 → [0.0, 0.25]`. Граница `dt=0` — дефект ниже |
| 6 | `.nowa` и файл без ключа | Pass. `test_setpoint_roundtrip_and_missing_field`: b0 `-0.2` / `0.05` сохраняется; без ключа b0 равен baseline |
| 7 | Энергия неудовлетворённой потребности; детерминизм при весе 0 | Pass. `test_unmet_need_still_costs_energy_while_asleep` (1x load и 10x). Два прогона с разным seed и `legacy_compat_weight=0`: оси, baseline и b0 совпали. Ген `af_baseline_adapt_rate` `[0, 0.01]`, дефолт `1/(6*3600)` |
| 8 | Colony `test_tc05` | Pass. К прежним ассертам (`last_seen_position == "wheel"`, `position_confidence < 0.5`) добавлена только заморозка `_is_emitting_alarm`. `test_tc08` по-прежнему зовёт `_perceive_alarm_calls`. Сценарий: stress `0.9`, позиция `wheel → house`, affect `fearful` |

Целевые тесты, exit 0: `tests/test_affective_time.py` — 10 passed; три теста Colony — 3 passed. Отрицательный `advance(-3)` ось, baseline и b0 не двигает. `deep_sleep(90 с, 3 цикла)` покрыт тестом: три шага по 30 с, `asleep=True`.

## Дефекты

### [MINOR] commit при host dt=0 продвигает аффект на 1 с

- Шаги: `step(..., decision_only=True, dt=0)` с ненулевым recall, затем `commit_executed_transition` без своего dt.
- Ожидалось: импульс recall без времени и одно продвижение на host dt `0`.
- Факт: вызовы `AffectiveSpace.step` — `[0.0, 1.0]`. Ноль в pending теряется из-за `or 1.0`.
- Где: `Agent.commit_executed_transition`, `pending.get("time_elapsed", 1.0) or 1.0`. То же для `step_elapsed`.
- Severity: minor

## Вопросы / блокеры

Нет. Заражение тревогой в демо и мультипоколенческие прогоны в этот чеклист не входили.

## Рекомендации

В commit проверять `None`, а не истинность числа, чтобы host `dt=0` оставался нулём. Положительные dt колонии (0.25 с и 2.5 с) этим не задеты.

## Готовность к релизу

С оговорками. Чеклист части 1 проходит; перед хостом, который может передать нулевой шаг, стоит закрыть minor.

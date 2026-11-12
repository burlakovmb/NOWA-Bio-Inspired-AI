# QA issue #68 — привязка sleep manager к восстановленному labile

Ветка: `team/68-sleep-manager-rebind`. Код: `959e191`, `17d50bc`. HEAD на момент прогона: `17d50bc`.
PR: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/70
Issue: https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/68
English: [issue-68-sleep-manager-rebind.en.md](issue-68-sleep-manager-rebind.en.md).

Код продукта в этом проходе не менялся. PR не создавался и не мержился. Полный `pytest` локально не запускался.

Машина: Python 3.12.3, pytest 9.2.0. Целевые тесты и пробы шли с `NOWA_STRICT_LEARNING=1`. Tamagochi: `use_pygame=False`, `use_gui=False`, `SDL_VIDEODRIVER=dummy` (mixer недоступен, агент всё равно поднялся).

## Вердикт

**PASS** (`17d50bc`).

`load_agent` после восстановления labile вызывает `_bind_restored_two_tier`. Менеджер, переданный аргументом, и `agent.sleep_manager`, если это другой объект, получают те же `labile` и `plasticity`, что сейчас лежат на агенте. `_host_agent` меняется только когда его нет или это уже этот агент. Формат pickle не расширялся: в сохранении по-прежнему ключ `labile_layer`. Файл без `labile_layer`, `plasticity_config` и `host_clock_s` поднимается пустым слоем, identity держится, `deep_sleep` не падает.

Прямой `SleepManager.deep_sleep` после load, без `Agent.sleep`, забирает восстановленный тег: Go `0.50 → 0.5800000000000001`, вклад эпизода исчезает, сторож на старом слое остаётся. `Agent.sleep` делает то же, когда слой уже принадлежит спящему агенту.

Employee `load_mind` и sandbox `restore_agent` больше не зовут свои хелперы. Identity, захват урока и привычки `vc_intent_memory` / `sandbox_intent_memory` на месте. По репозиторию вызовов `_rebind_sleep_manager` и `_rebind_learning_components` нет.

Tamagochi: после `_do_load_session` хозяин `nowa`, клетка и менеджер смотрят на один восстановленный слой, `_host_agent` — это `nowa`. `nowa.sleep()` и прямой `deep_sleep` этот слой не подменяют и съедают тег (канал `morning_awakening`, дельта Go `0.07999999999999996`).

CI pytest на PR #70 в единственном чтении был `pending`. Прогон не ждали.

## Покрытие

| # | Проверка | Результат |
| --- | --- | --- |
| 1 | save с непустым labile → load в свежего агента → `sleep_manager.labile is agent.labile`, то же для `plasticity` → один сон забирает тег | Pass. Прямой `deep_sleep(cycles=1)`: Go `0.5800000000000001`, вклад пуст. Сторожевой вклад остался на прежнем объекте слоя |
| 2 | Legacy pickle без `labile_layer` (также сняты `plasticity_config` и `host_clock_s`): пустой слой, identity, сон не падает | Pass. Вкладов нет. `_host_agent` — загруженный агент. `deep_sleep` без ошибки, Go `0.5700000000000001` (шаг сна без тега) |
| 3 | Прямой `deep_sleep` после load, без `Agent.sleep` | Pass. Тот же прогон, что пункт 1. Целевой тест дополнительно гоняет `Agent.sleep` и ждёт Go `0.58` |
| 4 | Employee `load_mind` и sandbox `restore_agent` без демо-хелперов: identity, захват урока, привычки intent-расширений | Pass. Employee: strength следа `0.2`, после `sleep(cycles=1)` вклад пуст, эпизод `consolidated`. Sandbox: три теста persistence |
| 5 | Tamagochi `_do_load_session` / `_rewire_two_tier_host`: после загрузки один слой, сон хозяина не откатывает на старый | Pass. См. ниже |
| 6 | `_host_agent` чужого хозяина не подменяется | Pass. Чужой хозяин остаётся. Пустой `_host_agent` заполняется загруженным агентом. Два разных менеджера получают восстановленный слой; у аргумента чужой хозяин сохраняется |
| 7 | В репозитории нет вызовов удалённых хелперов | Pass. Поиск `_rebind_sleep_manager` и `_rebind_learning_components` — 0 совпадений |
| 8 | CI на PR #70 | `pytest` **pending**. Run [43250793476](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/actions/runs/43250793476), job `131295708906`. Одно чтение, без ожидания |

Целевой pytest, корень репозитория, exit 0:

`python3 -m pytest -q --no-header -p no:warnings tests/test_issue13_two_tier.py::test_save_load_restores_labile_clock_and_config tests/test_issue13_two_tier.py::test_load_rebinds_sleep_manager_and_consolidates_restored_labile tests/test_issue13_two_tier.py::test_sleep_rebinds_manager_when_the_agent_layer_was_replaced tests/test_issue13_two_tier.py::test_load_keeps_a_foreign_sleep_manager_host "Demo/Virtual company/tests/test_employee_checkpoint_plasticity.py" "Demo/Virtual company/tests/test_sandbox_checkpoint.py::TestPersistence::test_resume_rebinds_custom_plasticity_and_pending_labile_tags" "Demo/Virtual company/tests/test_sandbox_checkpoint.py::TestPersistence::test_checkpoint_preserves_sleep_formed_habits_and_manager_reference" "Demo/Virtual company/tests/test_sandbox_checkpoint.py::TestPersistence::test_old_checkpoint_without_intent_extension_keeps_fresh_memory"`

**11 passed** in 0.27s.

Короткие пробы (не в репозитории): ядро (identity, прямой `deep_sleep`, legacy, чужой и пустой `_host_agent`, два менеджера), employee (`store_lesson` + `apply_outcome` под `learning_allowed`, strength `0.2`), живой `ChinchillaAgent`.

Не запускалось:

| # | Сценарий | Почему |
| --- | --- | --- |
| 1 | Полный `pytest` | Его гоняет CI на PR #70 |
| 2 | Много поколений, перебор сидов | Вне узкого чеклиста. Один эпизод, фиксированные seed в пробах |
| 3 | Интерактивный GUI Tamagochi | Контракт проверен на `ChinchillaAgent(use_pygame=False, use_gui=False)` |

### Tamagochi

`_do_load_session` передаёт в `load_agent` клетку (`agent=self`) и её `sleep_manager`, следующей строкой вызывает `_rewire_two_tier_host`. Других вызовов `load_agent` в демо нет. `_bind_two_tier_host` стоит в конструкторе раньше любой загрузки, так что `nowa` к моменту load уже есть.

До сохранения `source.labile is source.nowa.labile is source.sleep_manager.labile`. Канал `morning_awakening` стартует с Go `0.5805786188392569` (это вес клетки после конструктора, не `0.5` ядра). `nowa.commit_executed_transition` пишет вклад `ep-1`, reward `1.0`, стабильный Go не двигает. В гиппокампе 11 опытов; `td_committed_reward` есть только у `ep-1`.

После `_do_load_session` на свежей клетке: `nowa.labile is labile is sleep_manager.labile`, то же для `plasticity`, `_host_agent is nowa`, слой не тот объект, что был у хозяина до load, `ep-1` на месте.

`nowa.sleep(cycles=1)`: ошибки нет, слой тот же восстановленный, `_host_agent` по-прежнему `nowa`, вклада нет, Go `0.6605786188392568` (дельта `0.07999999999999996`, один незатухший шаг `+1`). Повтор на второй клетке через прямой `deep_sleep(cycles=1)` даёт те же identity и ту же дельту.

Между `load_agent` и `_rewire_two_tier_host` менеджер уже смотрит на восстановленный слой клетки, а `nowa.labile` ещё прежний, `_host_agent` остаётся `nowa`. Публичный `_do_load_session` это окно закрывает до возврата. Отдельный зонд ядра: `Agent.sleep` хозяина в этом окне возвращает менеджер на старый слой хозяина, восстановленный вклад не захватывается. После `_rewire_two_tier_host` окно закрыто, вклад ещё на месте.

## Дефекты

Дефектов по DoD нет.

## Рекомендации

`Agent.sleep` намеренно затирает `labile`, `plasticity` и `_host_agent` менеджера объектами спящего агента. Это фиксирует `test_sleep_rebinds_manager_when_the_agent_layer_was_replaced`. В окно между `load_agent` и `_rewire_two_tier_host` такой сон откатывает менеджер на старый слой хозяина. Сейчас между этими двумя вызовами в `_do_load_session` ничего нет. Туда не стоит вставлять сон или чтение менеджера.

`deep_sleep` выбирает эпизоды из hippocampus самого менеджера. Если передать менеджер, чей hippocampus не тот объект, что загружен в `load_agent`, привязанный слой виден, но тег не захватывается: вклад остаётся, Go канала `go` остаётся `0.5`, `_host_agent` чужого хозяина не меняется, опытов у менеджера `0`, у загруженного агента `1`. Employee, sandbox и Tamagochi так не собраны: hippocampus менеджера и аргумент `load_agent` — один объект.

`_bind_restored_two_tier` глотает любое исключение `setattr`. На обычном `SleepManager` этого не было.

## Готовность к релизу

Функциональный DoD на `17d50bc` выполнен. Релизный знак не ставлю, пока pytest CI на PR #70 не станет зелёным: в единственном чтении он был `pending`.

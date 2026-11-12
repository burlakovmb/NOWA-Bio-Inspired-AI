# Часы затухания гиппокампа при сохранении и загрузке

Дата: 2026-11-09. Статус: независимо подтверждён дефект сохранения уровня P2.
Проверенный коммит upstream: `ff01ddcd6966e7298ed789e33fd4106fb05d16da`;
дерево ядра: `0ca484475e9547fdab17a0c2b08638531500a25d`.
Отчёт не содержит данных Компании. Ядро не исправлялось.
Опубликованные доказательства: [дополнение к issue #16](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/16#issuecomment-6745692962).

В эпизоде сохраняется уже уменьшенная `activation_energy`, но не
`last_decay_ts` его signature. При восстановлении signature используется
`last_activated`, которое затухание не продвигает. Поэтому первое затухание
после загрузки может повторно учесть уже обработанный интервал.

## Минимальный синтетический контрпример

Один синтетический эпизод имеет энергию `1.0` и оба временных якоря в `t0`.
Строим signature, затем вызываем `_apply_decay()` в `t0 + 3600`.
Стандартное смешанное ядро даёт энергию `0.5485`. Сохраняем через
`AgentStorage.save_agent`, загружаем в новый `NOWAHippocampus` и восстанавливаем
signatures. В **тот же** момент `t0 + 3600` вызываем затухание у обоих экземпляров:

| Экземпляр | Энергия до вызова | Энергия после вызова |
|---|---:|---:|
| Непрерывный | 0.5485 | 0.5485 |
| Восстановленный | 0.5485 | 0.30085225 |

Между сравниваемыми вызовами время не проходит. Это исключает объяснение
только разным разбиением неэкспоненциального ядра на временные интервалы.
Agent, решения, обучение и сон не участвуют.

## Контракт в исходниках

- `src/hippocampus.py:535`: `_ensure_signature_store` восстанавливает энергию
  из эпизода, а якорь затухания — из `last_activated`.
- `src/hippocampus.py:625`: `_apply_decay` обновляет энергию эпизода и
  `last_decay_ts` signature; `last_activated` эпизода не меняется.
- `src/storage.py:16`: сохраняются experiences; якоря затухания signatures
  не включены. Сериализация эпизода сохраняет энергию и время активации.

Настройки конструктора гиппокампа также не сериализуются. Загрузка использует
настройки созданного вызывающей стороной объекта; она не сбрасывает существующий
host к defaults принудительно. Отдельный синтетический тест нестандартного
half-life показывает: новый стандартный host не восстанавливает half-life источника.

## Доказательства и ограничения

Самостоятельный пример ниже извлечён и успешно выполнен в проектной
`.venv`, со строгим режимом обучения и без записи bytecode. Он использует
настоящее сохранение ядра и затухание гиппокампа на синтетических данных.
Исходники продукта и ядра не менялись.

Независимая финальная QA воспроизвела сбой и прошла `18` синтетических
проверок. Инвариант продолжения в неизменный момент нарушен, как показано
выше. Код самостоятельного примера одинаков в обеих языковых версиях.

Это доказывает асимметрию сохранения, но не её влияние на выбор сотрудника.
Для корректного продолжения после перезапуска нужен контракт сохранения якоря
затухания вместе с уже уменьшенной энергией, включая legacy defaults и тесты
продолжения в неизменный момент времени. Контракт должен определить Maintainer;
замена `last_activated` часами затухания может изменить смысл этого поля.

## Самостоятельный контрпример

Запускать пример Python с каталогом `src` репозитория в `PYTHONPATH`.
Он создаёт и удаляет только временный синтетический checkpoint.

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
from unittest.mock import patch
from experience import Experience, Path as EventPath, Event, EventType
from hippocampus import NOWAHippocampus
from storage import AgentStorage

base = 1_790_000_000.0
with patch("time.time", return_value=base):
    episode = Experience(EventPath([Event("synthetic", EventType.CONTEXT)]))
episode.episode_id = "synthetic-1"
episode.activation_energy = 1.0
live = NOWAHippocampus()
live.experiences = [episode]
live._ensure_signature_store()
with patch("time.time", return_value=base + 3600):
    live._apply_decay()

with TemporaryDirectory(prefix="decay-contract-") as folder:
    storage = AgentStorage(folder)
    cortex = NS(patterns={})
    selector = NS(actions=[], confidence_threshold=0.0, action_metadata={})
    storage.save_agent(live, cortex, selector, filename="synthetic.pkl")
    restored = NOWAHippocampus()
    storage.load_agent(restored, cortex, selector, str(Path(folder) / "synthetic.pkl"))
    restored._ensure_signature_store()
    with patch("time.time", return_value=base + 3600):
        live._apply_decay()
        restored._apply_decay()
    continuous = live.experiences[0].activation_energy
    reloaded = restored.experiences[0].activation_energy
    assert abs(continuous - 0.5485) < 1e-12
    assert abs(reloaded - 0.30085225) < 1e-12
    print({"continuous": continuous, "reloaded": reloaded})
```

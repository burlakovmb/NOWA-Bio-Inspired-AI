# Затухание гиппокампа: доказательства и критерии issue #16

Дата: 2026-11-09. [Опубликованное дополнение к issue #16](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/16#issuecomment-6745692962).
Технический отчёт: [сохранение часов затухания](../qa/hippocampal-decay-persistence-2026-11-09.ru.md).

Документ фиксирует узкий контрпример и критерии принятия в рамках
существующей задачи сохранения. Текст между маркерами не изменён
относительно опубликованного двуязычного комментария.

<!-- github-body:start -->
### Описание
Это выполненный узкий контрпример для части [#16](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/16),
касающейся сохранения сигнатур гиппокампа. Существующая задача уже охватывает
потерю signatures при сохранении/загрузке; здесь добавлены доказательство
и явный критерий принятия внутри этой работы.

Уменьшенная затуханием `activation_energy` эпизода сохраняется, но
`last_decay_ts` его signature — нет. При загрузке signature использует
более старую `last_activated` как якорь затухания. В неизменный момент
она может повторно применить уже учтённый интервал.

### Доказательства в коде
Проверено на upstream main `ff01ddcd6966e7298ed789e33fd4106fb05d16da`
2026-11-09:
- [Сохраняемая часть гиппокампа](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/blob/ff01ddcd6966e7298ed789e33fd4106fb05d16da/src/storage.py#L28-L35).
- [Восстановление якоря затухания](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/blob/ff01ddcd6966e7298ed789e33fd4106fb05d16da/src/hippocampus.py#L578-L588).
- [Затухание меняет энергию и часы signature](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/blob/ff01ddcd6966e7298ed789e33fd4106fb05d16da/src/hippocampus.py#L640-L668).
- [Сериализация эпизода](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/blob/ff01ddcd6966e7298ed789e33fd4106fb05d16da/src/experience.py#L334-L341).

### Воспроизведение и статус проверки
Самостоятельный синтетический пример ниже использует только ядро. Каталог
`src` должен быть в `PYTHONPATH`. Записывается только временный checkpoint;
Agent не создаётся, решений, обучения, сна и прикладных данных нет.

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

Наблюдение: непрерывная энергия `0.5485`, восстановленная `0.30085225`.
Ожидание: сама граница загрузки должна оставить у обоих `0.5485` в этот
неизменный момент. Вторые вызовы получают совершенно одинаковые часы,
поэтому разное разбиение расписания затухания результат не объясняет.

Пример выполнен; независимая синтетическая проверка воспроизвела тот же
сбой. Это доказывает нарушение этого инварианта сохранения, но не влияние
на выбор сотрудника. Исторические значения давления из #16 не перепроверяются,
полная эквивалентность ума не устанавливается.

### Направление исправления и критерии принятия
Сохранять якорь затухания согласованно с уже уменьшенной энергией. Схему
и правило совместимости должен выбрать Maintainer; не подменять незаметно
смысл `last_activated`, обозначающего настоящую активацию.

- Сохранение/загрузка в неизменный момент и повторные циклы не должны
  применять затухание дважды.
- Непрерывный и восстановленный экземпляры должны совпадать после одинакового
  последующего интервала при одинаковой последовательности вызовов затухания.
- Для старых файлов без нового якоря нужна явная проверенная политика
  fallback/migration. Не заявлять, что несохранённый исторический якорь
  всегда можно восстановить точно.
- Сохранить идентичность эпизода, смысл времени активации и намеренную
  политику настенного времени ядра.

Полнота roundtrip состояния решений из #16 остаётся более широким критерием;
этот небольшой синтетический тест её дополняет.

### Приоритет / оценка
Предлагаемый приоритет: **medium**, как у #16; пакет работ **wp2**.
Трудоёмкость следует оценить вместе с #16/#31, без новой спекулятивной
оценки количества токенов.

### Связи и отдельные границы
- [#16](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/16): родительская работа по сохранению; предпочтительное место доказательства.
- [#31](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/31): безопасность формата может затронуть ту же схему, но этот контрпример не исправляет небезопасную десериализацию.
- [Уточнение объёма #14](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/14#issuecomment-6385597592): настенное время ядра намеренно; фиксация времени здесь — контроль теста, а не предложение менять эту политику.
- [#65](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/issues/65) / [PR #66](https://github.com/burlakovmb/NOWA-Bio-Inspired-AI/pull/66): сохранение генома/родословной колонии — другие данные и путь.
<!-- github-body:end -->

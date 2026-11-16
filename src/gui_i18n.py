"""English and Russian strings for the core Tk interface.

Source strings in ``src/gui.py`` stay the lookup keys. Stored affect axes,
drives, and action ids are not renamed; only the text drawn in the window
changes. Language precedence matches the demos: ``--lang``, then
``NOWA_LANG``, then English.
"""

from __future__ import annotations

import re

from nowa_i18n import get_language, reset_language, resolve_lang, set_language

SUPPORTED = ("en", "ru")

# Keyed display names. The key is the stored id.
TABLES: dict[str, dict[str, dict[str, str]]] = {
    "axis": {
        "en": {
            "valence": "Valence",
            "arousal": "Arousal",
            "activation": "Arousal",
            "threat": "Threat",
            "curiosity": "Curiosity",
            "dominance": "Dominance",
            "stress": "Stress",
            "trust": "Trust",
            "stability": "Stability",
            "attachment": "Attachment",
            "pleasure": "Pleasure",
            "pain": "Pain",
            "relaxation": "Relaxation",
            "focus": "Focus",
            "rejection": "Rejection",
            "vulnerability": "Vulnerability",
            "anxiety": "Anxiety",
            "tension": "Tension",
            "satisfaction": "Satisfaction",
            "interest": "Interest",
        },
        "ru": {
            "valence": "Валентность",
            "arousal": "Возбуждение",
            "activation": "Активация",
            "threat": "Угроза",
            "curiosity": "Любопытство",
            "dominance": "Доминирование",
            "stress": "Стресс",
            "trust": "Доверие",
            "stability": "Стабильность",
            "attachment": "Привязанность",
            "pleasure": "Удовольствие",
            "pain": "Боль",
            "relaxation": "Расслабление",
            "focus": "Фокус",
            "rejection": "Отторжение",
            "vulnerability": "Уязвимость",
            "anxiety": "Тревога",
            "tension": "Напряжение",
            "satisfaction": "Удовлетворение",
            "interest": "Интерес",
        },
    },
    "drive": {
        "en": {
            "curiosity": "curiosity",
            "social_drive": "social drive",
            "goal_tension": "goal tension",
            "exploration": "exploration",
            "energy_need": "energy need",
            "none": "none",
        },
        "ru": {
            "curiosity": "любопытство",
            "social_drive": "социальный драйв",
            "goal_tension": "напряжение цели",
            "exploration": "исследование",
            "energy_need": "потребность в энергии",
            "none": "нет",
        },
    },
    "action": {
        "en": {
            "ответить_кто_я": "say who I am",
            "сказать_привет": "say hello",
            "отказаться": "refuse",
            "помочь": "help",
            "задать_вопрос": "ask a question",
            "NO_ACTION": "no action",
            "undetermined": "undetermined",
            "explore": "explore",
            "approach": "approach",
            "eat": "eat",
            "rest": "rest",
            "hide": "hide",
            "sleep": "sleep",
            "none": "none",
            "auto": "auto",
        },
        "ru": {
            "ответить_кто_я": "ответить, кто я",
            "сказать_привет": "сказать привет",
            "отказаться": "отказаться",
            "помочь": "помочь",
            "задать_вопрос": "задать вопрос",
            "NO_ACTION": "нет действия",
            "undetermined": "не определено",
            "explore": "исследовать",
            "approach": "приблизиться",
            "eat": "есть",
            "rest": "отдыхать",
            "hide": "спрятаться",
            "sleep": "сон",
            "none": "нет",
            "auto": "авто",
        },
    },
    "mode": {
        "en": {
            "idle": "idle",
            "passive": "passive",
            "internal_processing": "internal cycle",
            "speaking": "speech",
            "low_energy": "low energy",
        },
        "ru": {
            "idle": "покой",
            "passive": "пассивный",
            "internal_processing": "внутренний цикл",
            "speaking": "речь",
            "low_energy": "низкая энергия",
        },
    },
    "failure": {
        "en": {
            "affect_mutation_outside_interface": "affect changed outside the interface",
            "internal_affect_apply_failed": "internal affect update failed",
            "invariant_violation": "invariant violation",
            "energy_deadlock": "energy deadlock",
            "unknown": "unknown",
        },
        "ru": {
            "affect_mutation_outside_interface": "аффект изменён вне интерфейса",
            "internal_affect_apply_failed": "не удалось применить внутренний аффект",
            "invariant_violation": "нарушение инварианта",
            "energy_deadlock": "тупик энергии",
            "unknown": "неизвестно",
        },
    },
    "emotion": {
        "en": {
            "joy": "joy",
            "sadness": "sadness",
            "love": "attachment",
            "hate": "rejection",
            "fear": "fear",
            "pleasure_rest": "calm",
            "interest": "interest",
            "tension": "tension",
            "anxiety": "anxiety",
            "unknown": "unknown",
            "none": "none",
        },
        "ru": {
            "joy": "радость",
            "sadness": "грусть",
            "love": "привязанность",
            "hate": "отторжение",
            "fear": "страх",
            "pleasure_rest": "спокойствие",
            "interest": "интерес",
            "tension": "напряжение",
            "anxiety": "тревога",
            "unknown": "неизвестно",
            "none": "нет",
        },
    },
}


def label(table: str, key: str, default: str | None = None) -> str:
    books = TABLES[table]
    lang = get_language()
    chosen = books.get(lang) or books["en"]
    if key in chosen:
        return chosen[key]
    if key in books["en"]:
        return books["en"][key]
    if default is not None:
        return default
    return str(key)


def _norm_id(value: object) -> str:
    key = str(value or "").strip()
    if key.startswith("background_"):
        key = key[len("background_") :]
    if key.startswith("bg_"):
        key = key[3:]
    return key


def axis_label(value: object) -> str:
    """Human-readable affect dimension. The stored axis id is unchanged."""

    key = _norm_id(value)
    if not key:
        return ""
    return label("axis", key, key.replace("_", " "))


def drive_label(value: object) -> str:
    key = str(value or "").strip() or "none"
    return label("drive", key, key.replace("_", " "))


def action_label(value: object) -> str:
    key = str(value or "").strip()
    if not key:
        return ""
    return label("action", key, key.replace("_", " "))


def mode_label(value: object) -> str:
    key = str(value or "").strip() or "idle"
    return label("mode", key, key.replace("_", " "))


def failure_label(value: object) -> str:
    key = str(value or "").strip() or "unknown"
    return label("failure", key, key.replace("_", " "))


def emotion_label(value: object) -> str:
    key = str(value or "").strip() or "unknown"
    return label("emotion", key, key.replace("_", " "))


PHRASES: dict[str, dict[str, str]] = {}


def _add(key: str, en: str, ru: str | None = None) -> None:
    PHRASES[key] = {"en": en, "ru": key if ru is None else ru}


# Window chrome. The key is the string currently written in src/gui.py.
_add("NOWA - Cognitive Agent Interface", "NOWA - Cognitive Agent Interface", "NOWA — интерфейс когнитивного агента")
_add("🤖 NOWA - Neural Memory Agent", "🤖 NOWA - Neural Memory Agent", "🤖 NOWA — агент нейронной памяти")
_add("Диалог:", "Dialog:")
_add("Ввод:", "Input:")
_add("Отправить", "Send")
_add("Очистить", "Clear")
_add("Действия", "Actions")
_add("Оценка ответа", "Response rating")
_add("Сохранить", "Save")
_add("Загрузить", "Load")
_add("Сохранить диалог", "Save dialog")
_add("Загрузить датасет", "Load dataset")
_add("Инспектор", "Inspector")
_add("Отправить оценку", "Send rating")
_add("Слой внешнего взаимодействия", "External interaction layer")
_add("источник:", "source:")
_add("неопр.:", "uncertainty:")
_add("данные JSON:", "JSON data:")
_add("Добавить наблюдение", "Add observation")
_add("Опрос среды", "Poll environment")
_add("действие:", "action:")
_add("приор:", "prior:")
_add("задержка:", "delay:")
_add("прогноз:", "forecast:")
_add("параметры JSON:", "JSON parameters:")
_add("Выполнить действие", "Run action")
_add("Обработать отложенные", "Resolve pending")
_add("Обновить статус", "Refresh status")
_add("набл:0 | ожидание:0 | шаг:0 | стратегии:0", "obs:0 | pending:0 | step:0 | strategies:0")
_add("обратная связь: н/д", "feedback: n/a")
_add("обратная связь: обработка...", "feedback: working...")
_add("❤️ Аффективное состояние", "❤️ Affective state")
_add("Валентность:", "Valence:")
_add("Валентность", "Valence")
_add("Активация:", "Arousal:")
_add("Активация", "Arousal")
_add("Угроза:", "Threat:")
_add("Угроза", "Threat")
_add("Любопытство:", "Curiosity:")
_add("Любопытство", "Curiosity")
_add("Аффективный фон:", "Affective background:")
_add("Тревога:", "Anxiety:")
_add("Тревога", "Anxiety")
_add("Напряжение:", "Tension:")
_add("Напряжение", "Tension")
_add("Удовлетворение:", "Satisfaction:")
_add("Удовлетворение", "Satisfaction")
_add("Интерес:", "Interest:")
_add("Интерес", "Interest")
_add("Аффективное пространство:", "Affective space:")
_add("Возбуждение:", "Arousal:")
_add("Возбуждение", "Arousal")
_add("Доминирование:", "Dominance:")
_add("Доминирование", "Dominance")
_add("Стресс:", "Stress:")
_add("Стресс", "Stress")
_add("Доверие:", "Trust:")
_add("Доверие", "Trust")
_add("Стабильность:", "Stability:")
_add("Стабильность", "Stability")
_add("Привязанность:", "Attachment:")
_add("Привязанность", "Attachment")
_add("Удовольствие:", "Pleasure:")
_add("Удовольствие", "Pleasure")
_add("Боль:", "Pain:")
_add("Боль", "Pain")
_add("Расслабление:", "Relaxation:")
_add("Расслабление", "Relaxation")
_add("Фокус:", "Focus:")
_add("Фокус", "Focus")
_add("Legacy overlay:", "Legacy axes:", "Прежние оси:")
_add("bias:", "bias:", "смещение:")
_add("bias: —", "bias: —", "смещение: —")
_add("Conflict:", "Conflict:", "Конфликт:")
_add("Conflict: 0.00", "Conflict: 0.00", "Конфликт: 0.00")
_add("Semantic Emotions:", "Semantic emotions:", "Смысловые эмоции:")
_add("(none)", "(none)", "(нет)")
_add("Эмоциональная память:", "Emotional memory:")
_add("Эмоциональные ожидания:", "Emotional expectations:")
_add("Регуляция ожиданий:", "Expectation regulation:")
_add("Мониторинг устойчивости:", "Stability monitoring:")
_add("Слой ценности (TD):", "Value layer (TD):")
_add("Данных пока нет", "No data yet")
_add("Нейромодуляторы:", "Neuromodulators:")
_add("Готовность:", "Readiness:")
_add("Не рассчитана", "Not computed")
_add("Автономный организм", "Autonomous organism")
_add("Режим: инициализация", "Mode: starting")
_add("Ведущий драйв: н/д", "Leading drive: n/a")
_add("тики:0", "ticks:0")
_add("ошибки:0", "errors:0")
_add("Энергия (автономная):", "Energy (autonomous):")
_add("Энергетическая усталость (автономная):", "Energy fatigue (autonomous):")
_add("Физиологическая усталость — в блоке бодрствования", "Physiological fatigue is in the wakefulness block")
_add("Авторежим: 1 тик = 1 секунда (реальное время)", "Auto mode: 1 tick = 1 second (wall clock)")
_add("Автономный режим: отключен", "Autonomous mode: off")
_add("😴 Состояние бодрствования", "😴 Wakefulness")
_add("Физиологическая усталость:", "Physiological fatigue:")
_add("Когнитивная надежность:", "Cognitive reliability:")
_add("1.00 (Полностью надежен)", "1.00 (Fully reliable)")
_add("0.00 (Полностью выспавшийся)", "0.00 (Fully rested)")
_add("Статистика времени:", "Time statistics:")
_add("Бодрствова: 0.0ч | Спал: 0.0ч", "Awake: 0.0h | Slept: 0.0h")
_add("💤 Быстрый сон (30м)", "💤 Short sleep (30m)")
_add("😴 Обычный сон (1ч)", "😴 Normal sleep (1h)")
_add("😪 Долгий сон (3ч)", "😪 Long sleep (3h)")
_add("⏱️ Временные уровни", "⏱️ Time scales")
_add("T0 (Мгновение):", "T0 (Moment):")
_add("T1 (Тренд):", "T1 (Trend):")
_add("T2 (Baseline - slow drift):", "T2 (Slow baseline):", "T2 (медленный фон):")
_add("T3 (Attractor - very slow):", "T3 (Very slow attractor):", "T3 (очень медленный аттрактор):")
_add("Окно T1:", "T1 window:")
_add("0/10 (скользящее)", "0/10 (sliding)")
_add("Всего шагов: 0", "Total steps: 0")
_add("📊 Статистика:", "📊 Statistics:")
_add("⏳ Время жизни агента:", "⏳ Agent lifetime:")
_add("🧠 Память:", "🧠 Memory:")
_add("Полностью выспавшийся", "Fully rested")
_add("Слегка усталый", "Slightly tired")
_add("Усталый", "Tired")
_add("Очень усталый", "Very tired")
_add("Истощенный", "Exhausted")
_add("Недежен", "Unreliable", "Ненадёжен")
_add("Ненадежен", "Unreliable")
_add("Средне", "Moderate")
_add("Надежен", "Reliable")
_add("Полностью надежен", "Fully reliable")
_add("✅ Высокая", "High")
_add("⚠️ Средняя", "Medium")
_add("❌ Низкая", "Low")
_add("Копировать", "Copy")
_add("Вырезать", "Cut")
_add("Вставить", "Paste")
_add("Выделить всё", "Select all")
_add("Сон", "Sleep")
_add("Ошибка сна", "Sleep error")
_add("Ошибка", "Error")
_add("Успех", "Success")
_add("Предупреждение", "Warning")
_add("Нет сохранений", "No saves")
_add("Внешнее наблюдение", "External observation")
_add("Внешнее действие", "External action")
_add("Критичные ошибки автономного организма", "Critical autonomous-organism errors")
_add("Инспектор состояния агента (NOWA Cognitive)", "Agent state inspector (NOWA Cognitive)")
_add("Эпизодическая память", "Episodic memory")
_add("Семантическая память", "Semantic memory")
_add("Выбор действий", "Action selection")
_add("Консолидация", "Consolidation")
_add("Привычки (IntentMemory)", "Habits (IntentMemory)")
_add("Статистика", "Statistics")
_add("🌙 Консолидация опытов в паттерны", "🌙 Consolidate experiences into patterns")
_add("🌙 Консолидация памяти (Сон)", "🌙 Memory consolidation (Sleep)")
_add("JSON files", "JSON files", "Файлы JSON")
_add("All files", "All files", "Все файлы")
_add("📂 Загрузка опыта из датасетов", "📂 Load experience from datasets")
_add("Загрузить состояние", "Load state")
_add("Закрыть", "Close")
_add("🌙 Начать консолидацию", "🌙 Start consolidation")
_add("Выберите сохранение:", "Choose a save:")
_add("Загрузить из папки datasets", "Load from the datasets folder")
_add("Загрузит все JSON файлы из папки datasets", "Loads every JSON file in the datasets folder")
_add("Загрузить из datasets", "Load from datasets")
_add("Загрузить конкретный файл", "Load one file")
_add("Выберите JSON файл датасета вручную", "Choose a dataset JSON file yourself")
_add("Выберите JSON файл датасета", "Choose a dataset JSON file")
_add("Выбрать файл", "Choose file")
_add("Загрузить из директории", "Load from a directory")
_add("Выберите папку с JSON файлами датасетов", "Choose a folder of dataset JSON files")
_add("Выберите папку с датасетами", "Choose a dataset folder")
_add("Выбрать папку", "Choose folder")
_add("📊 Состояние памяти", "📊 Memory state")
_add("⚙️ Параметры консолидации", "⚙️ Consolidation settings")
_add("Количество циклов сна:", "Sleep cycles:")
_add("(Каждый цикл: replay TD/BG → decay/normalize → кластеризация → консолидация)", "(Each cycle: TD/BG replay → decay/normalize → clustering → consolidation)")
_add("📈 Результаты консолидации", "📈 Consolidation results")
_add("⚠️ Функция устарела", "⚠️ Feature retired")
_add("режим:", "mode:")
_add("нагрузка:", "load:")
_add("цикл:", "cycle:")
_add("речь:", "speech:")
_add("ведущий:", "leading:")
_add("топ:", "top:")
_add("подавление:", "suppressed:")
_add("тики:", "ticks:")
_add("ошибки:", "errors:")
_add("набл:", "obs:")
_add("ожидание:", "pending:")
_add("шаг:", "step:")
_add("стратегии:", "strategies:")
_add("покой", "idle")
_add("пассивный", "passive")
_add("внутренний_цикл", "internal cycle")
_add("внутренняя_обработка", "internal processing")
_add("низкая_энергия", "low energy")
_add("нет", "none")
_add("н/д", "n/a")
_add("[AUTO] think: drive={drive} | action={action}", "[AUTO] think: drive={drive} | action={action}", "[AUTO] мысль: драйв={drive} | действие={action}")
_add("[AUTO] think: drive={drive} | action={action} | confidence={confidence:.2f}", "[AUTO] think: drive={drive} | action={action} | confidence={confidence:.2f}", "[AUTO] мысль: драйв={drive} | действие={action} | уверенность={confidence:.2f}")
_add("NO_ACTION (BG gate inhibited)", "no action (background gate inhibited)", "нет действия (фоновый контур заблокировал)")
_add("undetermined", "undetermined", "не определено")
_add("[AUTO] error: {error}", "[AUTO] error: {error}", "[AUTO] ошибка: {error}")
_add("[AUTO] tick x{ticks} | mode={mode} | load={load:.2f} | drive={drive} | energy={energy:.2f} | cycle={cycle}", "[AUTO] tick x{ticks} | mode={mode} | load={load:.2f} | drive={drive} | energy={energy:.2f} | cycle={cycle}", "[AUTO] тик x{ticks} | режим={mode} | нагрузка={load:.2f} | драйв={drive} | энергия={energy:.2f} | цикл={cycle}")
_add("[AUTO] {speech}", "[AUTO] {speech}", "[AUTO] {speech}")
_add("[AUTO speech] {speech}", "[AUTO speech] {speech}", "[AUTO речь] {speech}")
_add("Последнее действие:", "Last action:")
_add("Гиппокамп (шт):", "Hippocampus (count):")
_add("Кортекс (шт):", "Cortex (count):")
_add("Циклы сна:", "Sleep cycles:")
_add("Эпизодическая память:", "Episodic memory:")
_add("Опытов:", "Experiences:")
_add("Ср. подкр.:", "Mean reinforcement:")
_add("Семантическая память:", "Semantic memory:")
_add("Паттернов:", "Patterns:")
_add("Ср. сила:", "Mean strength:")
_add("Память привычек (IntentMemory):", "Habit memory (IntentMemory):")
_add("Привычек:", "Habits:")
_add("Процесс сна:", "Sleep process:")
_add("Циклов:", "Cycles:")
_add("🔗 Temporal Chains:", "🔗 Temporal chains:", "🔗 Временные цепочки:")
_add("Ср. стабильность:", "Mean stability:")
_add("ЭПИЗОДИЧЕСКАЯ ПАМЯТЬ (Hippocampus)", "EPISODIC MEMORY (Hippocampus)")
_add("Опыт #", "Experience #")
_add("Сигнатура:", "Signature:")
_add("События:", "Events:")
_add("Интенсивность:", "Intensity:")
_add("Подкрепление (раз):", "Reinforcement (times):")
_add("Последняя активация:", "Last activation:")
_add("Опытов нет. Отправьте сообщения агенту.", "No experiences yet. Send the agent a message.")
_add("СЕМАНТИЧЕСКАЯ ПАМЯТЬ (Cortex)", "SEMANTIC MEMORY (Cortex)")
_add("⚠ Паттерны создаются ТОЛЬКО во время сна (SleepManager)!", "⚠ Patterns are created ONLY during sleep (SleepManager)!")
_add("Используйте 🌙 Сон для консолидации опытов в паттерны.", "Use 🌙 Sleep to consolidate experiences into patterns.")
_add("Паттерн #", "Pattern #")
_add("Сила:", "Strength:")
_add("Создан:", "Created:")
_add("Паттернов нет. Запустите 🌙 Сон для консолидации.", "No patterns yet. Run 🌙 Sleep to consolidate.")
_add("ВЫБОР ДЕЙСТВИЙ (Action Selector)", "ACTION SELECTION (Action Selector)")
_add("⚠ Селектор НЕ ОБУЧАЕТСЯ! Выбор основан на:", "⚠ The selector DOES NOT LEARN. Choice is based on:")
_add("• Активации опытов в гиппокампе (давление)", "• Experience activation in the hippocampus (pressure)")
_add("• Паттернах в кортексе (смещение)", "• Cortical patterns (bias)")
_add("• Пороге уверенности (0.7)", "• Confidence threshold (0.7)")
_add("Доступные действия", "Available actions")
_add("Параметры:", "Parameters:")
_add("Порог уверенности:", "Confidence threshold:")
_add("Режим работы: Давление + смещение (без весов)", "Operating mode: pressure + bias (no weights)")
_add("🌙 КОНСОЛИДАЦИЯ И СОН (Sleep Manager)", "🌙 CONSOLIDATION AND SLEEP (Sleep Manager)")
_add("📍 Цикл сна: Воспроизведение → Кластеризация → Консолидация → Забывание", "📍 Sleep cycle: replay → clustering → consolidation → forgetting")
_add("📊 СТАТИСТИКА СНА:", "📊 SLEEP STATISTICS:")
_add("Всего циклов сна:", "Total sleep cycles:")
_add("Эпизодов в гиппокампе:", "Episodes in the hippocampus:")
_add("Паттернов в кортексе:", "Patterns in the cortex:")
_add("Коэффициент консолидации:", "Consolidation ratio:")
_add("⚙️  ПРОЦЕСС КОНСОЛИДАЦИИ:", "⚙️  CONSOLIDATION PROCESS:")
_add("1️⃣  Гиппокамп хранит недавние опыты", "1️⃣  The hippocampus stores recent experiences")
_add("2️⃣  Во время сна опыты кластеризуются по сходству", "2️⃣  During sleep, experiences cluster by similarity")
_add("3️⃣  Похожие кластеры консолидируются в паттерны", "3️⃣  Similar clusters consolidate into patterns")
_add("4️⃣  Нестабильные опыты забываются", "4️⃣  Unstable experiences are forgotten")
_add("АФФЕКТИВНОЕ СОСТОЯНИЕ (Affective Regulators)", "AFFECTIVE STATE (Affective Regulators)")
_add("❤️ Операциональные параметры регуляции поведения (БЕЗ субъективности)", "❤️ Operational parameters of behavior regulation")
_add("ТЕКУЩИЕ ПАРАМЕТРЫ:", "CURRENT PARAMETERS:")
_add("ПРОИЗВОДНЫЕ ПОКАЗАТЕЛИ:", "DERIVED MEASURES:")
_add("Серьезность конфликта:", "Conflict severity:")
_add("Готовность к адаптации:", "Adaptation readiness:")
_add("Модификатор давления:", "Pressure modifier:")
_add("АФФЕКТИВНОЕ ПРОСТРАНСТВО (Phase 4 pre):", "AFFECTIVE SPACE (Phase 4 pre):")
_add("Скорость V:", "Speed V:")
_add("Конфликт осей:", "Axis conflict:")
_add("SEMANTIC EMOTIONS (Phase 4.1):", "SEMANTIC EMOTIONS (Phase 4.1):", "СМЫСЛОВЫЕ ЭМОЦИИ (фаза 4.1):")
_add("Summary:", "Summary:", "Кратко:")
_add("STABILITY MONITORING (Phase 4.5):", "STABILITY MONITORING (Phase 4.5):", "МОНИТОРИНГ УСТОЙЧИВОСТИ (фаза 4.5):")
_add("СЛОЙ ЦЕННОСТИ (Phase 5.0):", "VALUE LAYER (Phase 5.0):")
_add("Оценка состояния:", "State value:")
_add("Ошибка прогноза (TD):", "Prediction error (TD):")
_add("Сдвиг дофамина от TD:", "Dopamine shift from TD:")
_add("Известных состояний:", "Known states:")
_add("Шагов обучения:", "Learning steps:")
_add("Слой ценности еще не обучался.", "The value layer has not learned yet.")
_add("АССОЦИАЦИИ С СУЩНОСТЯМИ:", "ENTITY ASSOCIATIONS:")
_add("Привязанность:", "Attachment:")
_add("Позитивные:", "Positive:")
_add("Негативные:", "Negative:")
_add("Нет записанных ассоциаций", "No associations recorded")
_add("АВТОНОМНЫЙ ОРГАНИЗМ (Spec v1):", "AUTONOMOUS ORGANISM (Spec v1):")
_add("Критичные ошибки:", "Critical errors:")
_add("Список критичных ошибок:", "Critical error list:")
_add("Критичных ошибок не зафиксировано.", "No critical errors recorded.")
_add("Предупреждения:", "Warnings:")
_add("Состояние агента сохранено!", "Agent state saved.")
_add("Ошибка при сохранении: {error}", "Save failed: {error}", "Ошибка при сохранении: {error}")
_add("Не найдены сохраненные файлы", "No saved files found")
_add("Выберите сохранение", "Choose a save")
_add("Состояние агента загружено!", "Agent state loaded.")
_add("Ошибка при загрузке: {error}", "Load failed: {error}", "Ошибка при загрузке: {error}")
_add("Диалог пуст", "The dialog is empty")
_add("История диалога сохранена!", "Dialog history saved.")
_add("Загружено {n} опытов из датасетов!", "Loaded {n} experiences from datasets.", "Загружено {n} опытов из датасетов!")
_add("Загружено {n} опытов из файла!", "Loaded {n} experiences from the file.", "Загружено {n} опытов из файла!")
_add("Загружено {n} опытов из директории!", "Loaded {n} experiences from the directory.", "Загружено {n} опытов из директории!")
_add("Сначала отправьте сообщение агенту", "Send the agent a message first")
_add("Агент спит {hours:.1f} часа(ов) ({minutes} минут)...", "The agent sleeps {hours:.1f} h ({minutes} min)...", "Агент спит {hours:.1f} ч ({minutes} мин)...")
_add("Ошибка: {error}", "Error: {error}", "Ошибка: {error}")
_add("[SYSTEM] Агент проснулся после {hours:.1f}ч сна.", "[SYSTEM] The agent woke after {hours:.1f}h of sleep.", "[SYSTEM] Агент проснулся после {hours:.1f} ч сна.")
_add("Вы: {user_input}", "You: {user_input}", "Вы: {user_input}")
_add("Ваша оценка: {rating}", "Your rating: {rating}", "Ваша оценка: {rating}")
_add("очень плохо (0.2)", "very bad (0.2)")
_add("плохо (0.4)", "bad (0.4)")
_add("нейтрально (0.6)", "neutral (0.6)")
_add("хорошо (0.8)", "good (0.8)")
_add("отлично (1.0)", "excellent (1.0)")
_add("прогноз награды", "reward forecast")
_add("прогноз награды: ожидается число или JSON ({error})", "reward forecast: expected a number or JSON ({error})", "прогноз награды: ожидается число или JSON ({error})")
_add("observation payload", "observation payload", "данные наблюдения")
_add("{field}: invalid JSON ({error})", "{field}: invalid JSON ({error})", "{field}: некорректный JSON ({error})")
_add("{field}: JSON object expected", "{field}: JSON object expected", "{field}: ожидался JSON-объект")
_add("ошибка статуса внешнего слоя: {error}", "external-layer status error: {error}", "ошибка статуса внешнего слоя: {error}")
_add("обратная связь: награда={reward:+.2f}, p={success:.2f}, задержка={delay}", "feedback: reward={reward:+.2f}, p={success:.2f}, delay={delay}", "обратная связь: награда={reward:+.2f}, p={success:.2f}, задержка={delay}")
_add("обратная связь: обработано={resolved}, награда={reward:+.2f}", "feedback: resolved={resolved}, reward={reward:+.2f}", "обратная связь: обработано={resolved}, награда={reward:+.2f}")
_add("Всего шагов: {n}", "Total steps: {n}", "Всего шагов: {n}")
_add("{count}/{capacity} (скользящее)", "{count}/{capacity} (sliding)", "{count}/{capacity} (скользящее)")
_add("Бодрствова: {awake:.1f}ч | Спал: {sleep:.1f}ч", "Awake: {awake:.1f}h | Slept: {sleep:.1f}h", "Бодрствование: {awake:.1f} ч | Сон: {sleep:.1f} ч")
_add("🧠 Во время сна опыты консолидируются в семантические паттерны.\nЭто ЕДИНСТВЕННЫЙ механизм обучения в NOWA!", "🧠 During sleep, experiences consolidate into semantic patterns.\nThis is the ONLY learning mechanism in NOWA.")
_add("РЕЗУЛЬТАТЫ:", "RESULTS:")
_add("Кандидатов в replay:", "Replay candidates:")
_add("Реплеев выполнено:", "Replays run:")
_add("Циклов с блокировкой replay:", "Cycles with replay blocked:")
_add("Оффлайн ΔV (сумма):", "Offline ΔV (sum):")
_add("Оффлайн ΔW (сумма):", "Offline ΔW (sum):")
_add("Кластеров создано:", "Clusters created:")
_add("Паттернов консолидировано:", "Patterns consolidated:")
_add("Нестабильных опытов забыто:", "Unstable experiences forgotten:")
_add("Циклов с decay:", "Cycles with decay:")
_add("Циклов с normalization:", "Cycles with normalization:")
_add("Sleep update count:", "Sleep update count:", "Число обновлений сна:")
_add("Последняя дисперсия Value:", "Last value variance:")
_add("Value variance ratio:", "Value variance ratio:", "Отношение дисперсии ценности:")
_add("Средний ACh за цикл:", "Mean ACh per cycle:")
_add("Средний ACh над baseline:", "Mean ACh above baseline:")
_add("ОБНОВЛЕННОЕ СОСТОЯНИЕ:", "UPDATED STATE:")
_add("Эпизодических воспоминаний:", "Episodic memories:")
_add("Семантических паттернов:", "Semantic patterns:")
_add("Всего циклов сна:", "Total sleep cycles:")
_add("Replay-состояние последнего цикла:", "Replay state of the last cycle:")
_add("Блокировка replay:", "Replay blocked:")
_add("Отобрано эпизодов:", "Episodes selected:")
_add("Выполнено replay:", "Replays completed:")
_add("Ошибка при консолидации: {error}", "Consolidation failed: {error}", "Ошибка при консолидации: {error}")
_add("❌ Ошибка при консолидации:", "❌ Consolidation failed:")
_add("💤 Запуск {cycles} цикла(ов) консолидации...", "💤 Starting {cycles} consolidation cycle(s)...", "💤 Запуск {cycles} цикла(ов) консолидации...")
_add("✅ Консолидация завершена: {cycles} цикл(ов), {patterns} паттернов", "✅ Consolidation finished: {cycles} cycle(s), {patterns} patterns", "✅ Консолидация завершена: {cycles} цикл(ов), {patterns} паттернов")
_add("Автоматическая тренировка селектора больше не поддерживается.", "Automatic selector training is no longer supported.")
_add(
    "В NOWA днём пишется лабильный слой (быстрые смещения Q и Go/NoGo); стабильная память консолидируется во сне.",
    "In NOWA, waking updates the labile layer (fast Q and Go/NoGo offsets); stable memory consolidates in sleep.",
)
_add("Используйте вместо этого:", "Use this instead:")
_add("1. 🌙 Сон - консолидирует опыты в паттерны", "1. 🌙 Sleep — consolidates experiences into patterns")
_add("2. Инспектор - смотрите состояние памяти", "2. Inspector — inspect memory state")
_add("Селектор действий НЕ имеет весов - он выбирает на основе давления активации!", "The action selector has NO weights. It chooses from activation pressure.")
_add("Я чувствую устойчивую смесь интереса и напряжения.", "I feel a steady mix of interest and tension.")
_add("Я чувствую смесь интереса и напряжения.", "I feel a mix of interest and tension.")
_add("Фоновая тревога доминирует.", "Background anxiety dominates.")
_add("Преобладает спокойное удовлетворение.", "Calm satisfaction predominates.")
_add("Преобладает интерес без выраженного напряжения.", "Interest predominates without marked tension.")
_add("Преобладает фоновый интерес.", "Background interest predominates.")
_add("Фоновое напряжение выражено.", "Background tension is pronounced.")
_add("Фоновое напряжение выражено сильнее интереса.", "Background tension outweighs interest.")
_add("Сейчас больше возбуждения, чем удовольствия — это похоже на ожидание.", "Arousal is higher than pleasure — this feels like anticipation.")
_add("Сейчас больше удовольствия, чем возбуждения — это похоже на удовлетворение.", "Pleasure is higher than arousal — this feels like satisfaction.")
_add("Боль заметнее удовольствия — это похоже на внутренний дискомфорт.", "Pain stands out over pleasure — this feels like inner discomfort.")
_add("Состояние спокойное и расслабленное.", "The state is calm and relaxed.")
_add("Присутствует спокойное удовлетворение.", "Calm satisfaction is present.")
_add("Есть навязчивые эмоциональные паттерны.", "There are obsessive emotional patterns.")
_add("Есть ощущение боли при слабом удовольствии.", "There is a sense of pain with little pleasure.")
_add("Есть ощущение отторжения и дистанции.", "There is a sense of rejection and distance.")
_add("Есть ощущение уязвимости.", "There is a sense of vulnerability.")
_add("Есть фоновая тревога, но она не доминирует.", "Background anxiety is present, but it does not dominate.")
_add("Есть фоновый интерес без выраженного напряжения.", "There is background interest without marked tension.")
_add("Присутствует привязанность, несмотря на внутренний конфликт.", "Attachment is present despite inner conflict.")
_add("Присутствует тёплая привязанность, несмотря на внутренний конфликт.", "Warm attachment is present despite inner conflict.")
_add("Состояние ровное и без выраженных доминант.", "The state is even, without a strong dominant.")
_add("Фокус повышен, внимание собрано.", "Focus is high and attention is gathered.")
_add("Есть навязчивый эмоциональный паттерн.", "There is an obsessive emotional pattern.")
_add("Радость и напряжение часто проявляются вместе.", "Joy and tension often appear together.")
_add("Состояние устойчиво.", "The state is stable.")
_add("Существует риск повторения навязчивого паттерна.", "There is a risk of repeating an obsessive pattern.")
_add("Эмоциональная динамика вероятно стабилизируется.", "Emotional dynamics will probably settle.")
_add("Эмоциональная динамика выглядит нестабильной.", "Emotional dynamics look unstable.")
_add("Эмоциональная динамика может усиливаться.", "Emotional dynamics may intensify.")
_add("Слой стабильности: отклонений не обнаружено.", "Stability layer: no deviations found.")
_add("Ожидания и результат почти совпали.", "Expectations and the outcome nearly matched.")
_add("Отрицательный сюрприз: результат хуже ожиданий.", "Negative surprise: the outcome was worse than expected.")
_add("Положительный сюрприз: результат лучше ожиданий.", "Positive surprise: the outcome was better than expected.")
_add("NOWA — one agent, awake. No backprop, no language model.", "NOWA — one agent, awake. No backprop, no language model.", "NOWA — один агент, бодрствует. Без обратного распространения и без языковой модели.")
_add("affect (8): {axes}", "affect (8): {axes}", "аффект (8): {axes}")
_add("modulators: {mods}", "modulators: {mods}", "модуляторы: {mods}")
_add("wake {index}: context={context}  reward={reward:+.2f}  action={action}", "wake {index}: context={context}  reward={reward:+.2f}  action={action}", "бодрствование {index}: контекст={context}  награда={reward:+.2f}  действие={action}")
_add("Sleep. Slow memory consolidates here; waking did not train weights.", "Sleep. Slow memory consolidates here; waking did not train weights.", "Сон. Здесь консолидируется медленная память; бодрствование веса не обучает.")
_add("sleep cycles reported: {cycles}", "sleep cycles reported: {cycles}", "сообщено циклов сна: {cycles}")
_add("episodes stored: {n}", "episodes stored: {n}", "сохранено эпизодов: {n}")
_add(
    "genome: {n} genes. offspring generation={generation} (sister={sister}), one gene neuromodulator DA/NE weight ({gene}) daughter={daughter:+.3f} son={son:+.3f}",
    "genome: {n} genes. offspring generation={generation} (sister={sister}), one gene neuromodulator DA/NE weight ({gene}) daughter={daughter:+.3f} son={son:+.3f}",
    "геном: {n} генов. поколение потомка={generation} (сестра={sister}), один ген вес нейромодулятора DA/NE ({gene}) дочь={daughter:+.3f} сын={son:+.3f}",
)
_add(
    "epigenome: {n} consolidated pattern(s) eligible to pass to offspring.",
    "epigenome: {n} consolidated pattern(s) eligible to pass to offspring.",
    "эпигеном: {n} консолидированных паттерна(ов) могут перейти потомству.",
)
_add(
    "Next: PYTHONPATH=\"Demo/Colony chinchillas/src\" python3 -m colony_gui --headless --agents 4 --duration 2",
    "Next: PYTHONPATH=\"Demo/Colony chinchillas/src\" python3 -m colony_gui --headless --agents 4 --duration 2",
    "Дальше: PYTHONPATH=\"Demo/Colony chinchillas/src\" python3 -m colony_gui --headless --agents 4 --duration 2",
)
_add("Run the NOWA cognitive interface", "Run the NOWA cognitive interface", "Запустить когнитивный интерфейс NOWA")
_add("Run a short NOWA agent episode", "Run a short NOWA agent episode", "Короткий прогон агента NOWA")
_add("UI language. Overrides NOWA_LANG.", "UI language. Overrides NOWA_LANG.", "Язык интерфейса. Важнее NOWA_LANG.")

_KEYS_BY_LEN = tuple(sorted(PHRASES, key=len, reverse=True))
_ID_TABLES = ("action", "drive", "mode", "failure")
_ID_TOKENS = []
for _table in _ID_TABLES:
    for _ident in TABLES[_table]["en"]:
        # Whole-word swaps are only for stored ids that are not ordinary words.
        # Affect axes are labeled at the widget that draws them.
        if "_" in _ident or _ident in {"NO_ACTION"}:
            _ID_TOKENS.append(_ident)
_ID_TOKENS = tuple(sorted(set(_ID_TOKENS), key=len, reverse=True))
_ID_RE = re.compile(r"(?<![\w])(" + "|".join(re.escape(tok) for tok in _ID_TOKENS) + r")(?![\w])")


def tr(text: str, **kwargs: object) -> str:
    """Translate a source phrase into the active language."""

    if text is None:
        return ""
    raw = str(text)
    entry = PHRASES.get(raw)
    translated = entry[get_language()] if entry else raw
    if kwargs:
        try:
            return translated.format(**kwargs)
        except Exception:
            return translated
    return translated


def _replace_bounded(text: str, source: str, target: str) -> str:
    if source == target or source not in text:
        return text
    pattern = re.compile(r"(?<![\w])" + re.escape(source) + r"(?![\w])")
    return pattern.sub(lambda _match: target, text)


def translate_block(text: str) -> str:
    """Translate source-language phrases and known ids inside a text block.

    Call this on text that was just built from the source strings, not on
    text that was already translated.
    """

    if not text:
        return ""
    rendered = str(text)
    lang = get_language()
    for key in _KEYS_BY_LEN:
        target = PHRASES[key][lang]
        rendered = _replace_bounded(rendered, key, target)

    def _swap(match: re.Match[str]) -> str:
        token = match.group(1)
        for table in _ID_TABLES:
            books = TABLES[table][lang]
            if token in books:
                return books[token]
        return token

    return _ID_RE.sub(_swap, rendered)


def format_auto_thought(active_drive: object, best_action: object, confidence: float | None) -> str:
    """User-facing autonomous thought line. Stored ids are not changed."""

    drive = drive_label(active_drive)
    raw_action = str(best_action or "").strip()
    if raw_action == "NO_ACTION":
        action = tr("NO_ACTION (BG gate inhibited)")
    elif raw_action:
        action = action_label(raw_action)
    else:
        action = tr("undetermined")
    if confidence is None:
        return tr("[AUTO] think: drive={drive} | action={action}", drive=drive, action=action)
    return tr(
        "[AUTO] think: drive={drive} | action={action} | confidence={confidence:.2f}",
        drive=drive,
        action=action,
        confidence=confidence,
    )


def assert_catalog_parity() -> None:
    """English and Russian catalogs cover the same keys and are non-empty."""

    for table, books in TABLES.items():
        if set(books["en"]) != set(books["ru"]):
            raise AssertionError(f"{table} EN/RU keys differ")
        for lang in ("en", "ru"):
            for key, value in books[lang].items():
                if not str(value).strip():
                    raise AssertionError(f"empty {table}.{lang}.{key}")
    for key, entry in PHRASES.items():
        if set(entry) != {"en", "ru"}:
            raise AssertionError(f"phrase {key!r} is missing a language")
        if not entry["en"].strip() or not entry["ru"].strip():
            raise AssertionError(f"empty phrase {key!r}")


__all__ = [
    "PHRASES",
    "TABLES",
    "action_label",
    "assert_catalog_parity",
    "axis_label",
    "drive_label",
    "emotion_label",
    "format_auto_thought",
    "get_language",
    "label",
    "mode_label",
    "reset_language",
    "resolve_lang",
    "set_language",
    "tr",
    "translate_block",
]

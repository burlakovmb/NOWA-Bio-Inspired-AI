## Аннотация

English version: [NOWA_Virtual_Employees_Architecture_Spec.en.md](NOWA_Virtual_Employees_Architecture_Spec.en.md)

Архитектурная спецификация задаёт компанию из независимых экземпляров NOWA, для которых инструменты MCP являются органами тела, а не вызовами, видимыми когнитивному ядру. Наследуемые принципы сохраняют суверенитет агента, консолидацию исключительно в `sleep_cycle`, выбор намерения без порождения текста ядром и обязательный путь от базальных ганглиев к таламическому шлюзу. Отдельный принцип этой линии отделяет деньги от валентности: бюджет и шлюз одобрения лежат вне когнитивного контура, наравне с физикой внешнего отказа. Орган описывается записью `MCPCapability` с уровнем риска от чтения до необратимой записи. Эвристика по имени инструмента лишь предлагает класс и требует человеческого подтверждения до выдачи доступа, особенно для высокой и необратимой записи. Сенсорный кодировщик переводит исход вызова в токены контекста и аффективный импульс по карте бизнес-событий. В приведённой карте закупок критически низкий запас имеет валентность −0,7 и возбуждение 0,8, превышение бюджета — −0,8 и 0,7, благоприятное закрытие сделки — 0,8 и 0,6.

Ввод разделён на три стадии. Стадия 1 — песочница: один агент проживает кварталы симулированного рынка до контакта с реальными данными. Эскиз конфигурации в этом документе задаёт бюджет 100 000, десять товаров, пять поставщиков, квартал в девяносто дней и вероятность шока спроса 0,05; исполнение заказа в песочнице мгновенно. Стадия 2 читает реальные данные MCP, оставляет чтение свободным с первого дня и проводит любую запись через `ApprovalGate` со статусами ожидания, одобрения, отказа, правки человеком и истечения срока. Стадия 3 делает автономию свойством отдельной возможности, а не режима агента целиком. Пример политики в тексте: заказы до 500 долл. у поставщиков с репутацией выше 0,7 могут исполняться без очереди при дополнительном условии разрешения; выборочная последующая проверка задана долей 10 %; сохраняются мгновенный отзыв всех разрешений, потолок бюджета вне воли агента, неизменяемый журнал и истечение разрешения с повторным подтверждением.

Несколько сотрудников определены как несколько экземпляров, не разделяющих память; их взаимодействие идёт через тот же внешний мир. Многоагентная организация отнесена к шагу после первого сотрудника. Тем самым документ отделяет учебный контур песочницы от последующего протокольного тела, в котором запись проходит шлюз, а ядро остаётся не импортирующим протокол.

# NOWA Virtual Employees — Архитектурная спецификация

**Версия:** 1.0
**Статус:** Foundational architecture — требует детализации по модулям
**Цель:** Автономная компания из независимых NOWA-агентов, взаимодействующих
с внешним миром через MCP как "тело" когнитивного "мозга"

---

## 0. Наследуемые принципы (не подлежат пересмотру)

Эти принципы установлены в предыдущих спецификациях NOWA и остаются в силе:

1. **Агент — суверенная единица.** Нет центрального контроллера. Каждый
   виртуальный сотрудник — независимый экземпляр NOWA со своим гиппокампом,
   аффективным пространством, нейромодуляторами, геномом.
2. **Обучение только во сне.** `sleep_manager.sleep_cycle()` — единственный
   механизм консолидации. Во время рабочего дня (waking) агент не меняет веса.
   С #13: дневные исходы идут в лабильный слой, стабильные значения меняются только в `Agent.sleep()`; хост сотрудника передаёт `dt` ([issue-13-demo-virtual-company.ru.md](../../../Docs/specs/issue-13-demo-virtual-company.ru.md)).
3. **NOWA не генерирует текст.** Она выбирает из `RealizationExperience` /
   принимает решения о *намерении*. Формулировка текста — отдельный слой
   (см. раздел 4).
4. **BasalGanglia → Thalamic Gate обязателен.** Любое действие агента проходит
   через Go/NoGo решение, прежде чем стать `ActionIntent`.

### Новый принцип для этого проекта

5. **Деньги — не то же самое, что валентность.** Финансовые ограничения
   (бюджет, approval gates) находятся **вне** когнитивного контура агента —
   это не часть мозга, это часть физической реальности тела, как гравитация.
   Агент не может "передумать" бюджетный лимит силой воли — так же как
   не может передумать физику MCP-вызова, который возвращает ошибку 403.

---

## 1. Концептуальная модель: тело и мозг

```
                    ┌─────────────────────────────┐
                    │   ЧЕЛОВЕЧЕСКИЙ КОНТРОЛЬ       │
                    │  (approval gate, kill switch, │
                    │   budget ceiling, audit)       │
                    └──────────────┬────────────────┘
                                   │ невозможно обойти
                    ┌──────────────▼────────────────┐
                    │   ВНЕШНИЙ МИР (MCP-серверы)     │
                    │  1С / ERP / email / Slack /     │
                    │  supplier API / calendar /      │
                    │  payment gateway                │
                    └──────────────┬────────────────┘
                                   │
        ┌──────────────────────────▼──────────────────────────┐
        │              ТЕЛО (Body Layer — новое)                 │
        │  ┌────────────────┐         ┌────────────────────┐    │
        │  │ Sensory Adapter │         │  Motor Adapter       │   │
        │  │ MCP result →     │         │  ActionIntent →      │   │
        │  │ context_events + │         │  MCP tool call +     │   │
        │  │ affective impulse│         │  approval routing    │   │
        │  └────────┬─────────┘         └──────────▲──────────┘   │
        └───────────┼───────────────────────────────┼──────────────┘
                     │                               │
        ┌────────────▼───────────────────────────────┴──────────────┐
        │                МОЗГ (NOWA Agent — без изменений ядра)         │
        │  hippocampus → affective_space → selector →                  │
        │  BG/Thalamic Gate → ActionIntent                              │
        │  (sleep_manager консолидирует опыт дня по ночам)              │
        └────────────────────────────────────────────────────────────┘
```

**Ключевая метафора:** MCP-тулы — это не API, это органы чувств и мышцы.
Email-тул — не "интеграция с почтой", это "рука, которая может написать
письмо". Агент не знает, что такое "MCP" — он знает, что может "посмотреть
остатки на складе" и "написать поставщику". Абстракция MCP спрятана
полностью внутри Sensory/Motor Adapter.

---

## 2. Универсальный MCP Body Layer

### 2.1 Почему универсальность важна с первого дня

Если адаптер жёстко привязать к 1С, то каждый новый сотрудник (продажник,
бухгалтер, HR) потребует переписывания слоя тело-мозг с нуля. Вместо этого
нужна декларативная модель: "какие органы чувств и мышцы доступны этому
конкретному агенту" описывается конфигурацией, а не кодом.

### 2.2 `MCPCapability` — универсальное описание одного MCP-инструмента

```python
"""nowa_body/mcp_capability.py"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class CapabilityRisk(Enum):
    """Классификация риска инструмента — определяет approval routing."""
    READ_ONLY = "read_only"       # чтение данных, риска нет
    LOW_WRITE = "low_write"       # черновик документа, не отправлен
    MEDIUM_WRITE = "medium_write" # отправка письма, создание заявки
    HIGH_WRITE = "high_write"     # оплата, изменение цены контракта
    IRREVERSIBLE = "irreversible" # удаление данных, финальное подтверждение сделки


@dataclass
class MCPCapability:
    """
    Универсальное описание одного MCP-инструмента как 'органа' агента.

    Заполняется при регистрации MCP-сервера, не хардкодится под конкретную
    систему (1С, email и т.д. — это конкретные *инстансы* этого описания).
    """
    tool_id: str                       # уникальный id: "mcp__1c__get_stock_levels"
    server_name: str                   # "1c_erp", "email", "supplier_api"
    display_name: str                  # человекочитаемое имя
    description: str                   # что делает инструмент
    risk_level: CapabilityRisk
    domain_tags: List[str] = field(default_factory=list)  # ["procurement", "finance"]
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    requires_approval: bool = True     # переопределяется risk_level, но explicit override возможен
    cost_impact_estimate: Optional[str] = None  # "none" | "low" | "medium" | "high"
    max_autonomous_value: Optional[float] = None  # если сумма < этого — может быть автономным

    def __post_init__(self) -> None:
        # Безопасный дефолт: любой WRITE-риск требует approval,
        # пока явно не разрешено обратное на Stage 3.
        if self.risk_level in (
            CapabilityRisk.MEDIUM_WRITE,
            CapabilityRisk.HIGH_WRITE,
            CapabilityRisk.IRREVERSIBLE,
        ):
            self.requires_approval = True
```

### 2.3 `MCPToolRegistry` — реестр доступных органов для агента

```python
"""nowa_body/tool_registry.py"""

from typing import Dict, List, Optional
from .mcp_capability import MCPCapability, CapabilityRisk


class MCPToolRegistry:
    """
    Хранит capability-описания для одного агента (одного сотрудника).

    Каждый агент имеет СВОЙ реестр — это часть суверенности:
    менеджер по закупкам не видит инструменты бухгалтера.
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self._capabilities: Dict[str, MCPCapability] = {}

    def register(self, capability: MCPCapability) -> None:
        self._capabilities[capability.tool_id] = capability

    def register_from_mcp_discovery(self, mcp_client: Any) -> int:
        """
        Автоматически строит capability-описания из MCP tool discovery.
        Использует heuristics для risk_level если сервер не предоставляет
        явных метаданных (см. раздел 2.4 — эвристики классификации риска).
        """
        raise NotImplementedError("реализуется под конкретный MCP client SDK")

    def get(self, tool_id: str) -> Optional[MCPCapability]:
        return self._capabilities.get(tool_id)

    def list_by_risk(self, risk: CapabilityRisk) -> List[MCPCapability]:
        return [c for c in self._capabilities.values() if c.risk_level == risk]

    def list_by_domain(self, domain_tag: str) -> List[MCPCapability]:
        return [c for c in self._capabilities.values() if domain_tag in c.domain_tags]

    def sensory_capabilities(self) -> List[MCPCapability]:
        """Только READ_ONLY — то, чем агент может 'смотреть' на мир."""
        return self.list_by_risk(CapabilityRisk.READ_ONLY)

    def motor_capabilities(self) -> List[MCPCapability]:
        """Всё, что изменяет внешний мир."""
        return [
            c for c in self._capabilities.values()
            if c.risk_level != CapabilityRisk.READ_ONLY
        ]
```

### 2.4 Эвристики автоклассификации риска (для универсальности)

Когда новый MCP-сервер подключается (1С, потом CRM, потом что угодно),
нужна эвристика для первичной классификации без ручной разметки каждого тула:

```python
"""nowa_body/risk_classifier.py"""

RISK_KEYWORDS = {
    CapabilityRisk.READ_ONLY: [
        "get_", "list_", "search_", "read_", "fetch_", "query_",
        "check_", "view_",
    ],
    CapabilityRisk.LOW_WRITE: [
        "draft_", "prepare_", "compose_", "generate_document_",
    ],
    CapabilityRisk.MEDIUM_WRITE: [
        "send_", "create_order_", "submit_", "post_", "update_",
    ],
    CapabilityRisk.HIGH_WRITE: [
        "pay_", "transfer_", "approve_payment_", "sign_contract_",
        "change_price_",
    ],
    CapabilityRisk.IRREVERSIBLE: [
        "delete_", "cancel_contract_", "terminate_", "revoke_",
    ],
}

def classify_risk_heuristic(tool_name: str, description: str) -> CapabilityRisk:
    """
    Первичная эвристическая классификация по имени инструмента.

    ВАЖНО: это только default. Человек-администратор ДОЛЖЕН явно
    подтвердить или скорректировать классификацию перед тем, как
    агент получит доступ к инструменту (см. раздел 6 — Governance).
    Никогда не полагаться на эвристику для HIGH_WRITE/IRREVERSIBLE
    без человеческого review.
    """
    name_lower = tool_name.lower()
    # Проверяем от самого опасного к самому безопасному —
    # fail-safe в сторону большей осторожности при неоднозначности
    for risk in (
        CapabilityRisk.IRREVERSIBLE,
        CapabilityRisk.HIGH_WRITE,
        CapabilityRisk.MEDIUM_WRITE,
        CapabilityRisk.LOW_WRITE,
        CapabilityRisk.READ_ONLY,
    ):
        if any(kw in name_lower for kw in RISK_KEYWORDS[risk]):
            return risk
    # Неизвестный паттерн → максимальная осторожность
    return CapabilityRisk.HIGH_WRITE
```

---

## 3. Sensory Adapter — MCP-результат → аффективный импульс

### 3.1 Принцип (наследуется из Warriner-демо)

Так же, как `WordStimulusEncoder` конвертировал слово в `context_events`,
здесь `BusinessEventEncoder` конвертирует результат MCP-вызова в
`context_events` + аффективный сигнал через тот же путь — **активацию
гиппокампа**, не прямую инъекцию.

### 3.2 `ToolAffectiveMapping` — конфигурируемая карта событие → аффект

```yaml
# configs/procurement_affective_mapping.yaml
#
# Аналог Warriner-словаря, но для бизнес-событий.
# Формат: событие → базовый VAD-сигнал (до прохождения через seed-память).
# Используется HippocampusSeeder для посева "профессиональной интуиции" —
# см. раздел 5.

events:
  invoice_overdue:
    valence: -0.6
    arousal: 0.7
    dominance: 0.3
    tags: [finance, urgency, risk]

  supplier_price_increase:
    valence: -0.4
    arousal: 0.5
    dominance: 0.4
    tags: [procurement, cost]

  deal_closed_favorable:
    valence: 0.8
    arousal: 0.6
    dominance: 0.7
    tags: [procurement, success]

  stock_critical_low:
    valence: -0.7
    arousal: 0.8
    dominance: 0.2
    tags: [procurement, urgency, risk]

  supplier_reliability_confirmed:
    valence: 0.5
    arousal: 0.3
    dominance: 0.6
    tags: [procurement, trust]

  budget_exceeded:
    valence: -0.8
    arousal: 0.7
    dominance: 0.2
    tags: [finance, risk, conflict]

  new_supplier_unverified:
    valence: -0.1
    arousal: 0.5
    dominance: 0.3
    tags: [procurement, novelty, risk]

  contract_renewed:
    valence: 0.6
    arousal: 0.3
    dominance: 0.7
    tags: [procurement, stability]
```

### 3.3 `BusinessEventEncoder`

```python
"""nowa_body/sensory_adapter.py"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class BusinessEventImpulse:
    """Аналог AffectiveImpulse из Warriner-демо, для бизнес-событий."""
    event_name: str
    valence: float
    arousal: float
    dominance: float
    source_tool: str
    raw_payload: Dict[str, Any]
    tags: List[str]


class BusinessEventEncoder:
    """
    Конвертирует результат MCP tool call → context_events для NOWA.

    Работает по той же схеме, что WordStimulusEncoder:
    - НЕ инжектирует VAD напрямую в affective_space
    - Строит context_events, которые активируют гиппокамп
    - Гиппокамп должен быть предварительно засеян через
      HippocampusSeeder (раздел 5), иначе — нулевая активация
    """

    def __init__(self, affective_mapping: Dict[str, dict]):
        self.affective_mapping = affective_mapping

    def encode_tool_result(
        self,
        tool_id: str,
        result: Dict[str, Any],
        event_classifier: Optional[Any] = None,
    ) -> List[str]:
        """
        1. Классифицировать результат MCP-вызова в одно или несколько
           именованных бизнес-событий (event_classifier — доменная логика,
           специфичная для каждой роли, см. раздел 3.4)
        2. Для каждого события построить context_events токены
           (аналог _word_to_events из Warriner-демо)
        """
        events = self._classify_events(tool_id, result, event_classifier)
        tokens: List[str] = []
        for event_name in events:
            tokens.extend(self._event_to_tokens(event_name))
        return tokens

    def _classify_events(
        self,
        tool_id: str,
        result: Dict[str, Any],
        event_classifier: Optional[Any],
    ) -> List[str]:
        if event_classifier is not None:
            return event_classifier(tool_id, result)
        # Fallback: имя тула как есть, если нет доменного классификатора
        return [tool_id.split("__")[-1]]

    def _event_to_tokens(self, event_name: str) -> List[str]:
        entry = self.affective_mapping.get(event_name)
        if entry is None:
            return [f"event:{event_name}"]

        tokens = [f"event:{event_name}"]
        v = float(entry.get("valence", 0.0))
        a = float(entry.get("arousal", 0.5))

        if v > 0.5:
            tokens.append("valence:very_positive")
        elif v > 0.15:
            tokens.append("valence:positive")
        elif v < -0.5:
            tokens.append("valence:very_negative")
        elif v < -0.15:
            tokens.append("valence:negative")
        else:
            tokens.append("valence:neutral")

        if a > 0.6:
            tokens.append("arousal:high")

        for tag in entry.get("tags", []):
            tokens.append(f"domain:{tag}")

        return tokens
```

### 3.4 Доменный классификатор событий (пример для закупок)

```python
"""nowa_roles/procurement/event_classifier.py"""

def classify_procurement_events(tool_id: str, result: dict) -> list:
    """
    Специфичная для роли логика: превращает сырой MCP-ответ
    в именованные бизнес-события из affective_mapping.

    Это единственное место в системе, где есть доменное знание
    "что значит этот ответ 1С для закупщика". Другие роли
    (продажи, бухгалтерия) будут иметь свой classifier.
    """
    events = []

    if "get_stock_levels" in tool_id:
        for item in result.get("items", []):
            if item.get("quantity", 0) < item.get("reorder_point", 0):
                events.append("stock_critical_low")

    if "get_invoices" in tool_id:
        for invoice in result.get("invoices", []):
            if invoice.get("days_overdue", 0) > 0:
                events.append("invoice_overdue")

    if "get_supplier_quote" in tool_id:
        quote = result.get("quote", {})
        prev_price = quote.get("previous_price")
        curr_price = quote.get("current_price")
        if prev_price and curr_price and curr_price > prev_price * 1.05:
            events.append("supplier_price_increase")
        if quote.get("supplier_is_new"):
            events.append("new_supplier_unverified")

    if "get_budget_status" in tool_id:
        if result.get("spent", 0) > result.get("allocated", float("inf")):
            events.append("budget_exceeded")

    return events or ["neutral_observation"]
```

---

## 4. Motor Adapter — ActionIntent → MCP tool call

### 4.1 Разделение "решить" и "сформулировать"

Как оговорено в принципе 3 (раздел 0): NOWA решает **намерение**
(`ActionIntent`: "написать поставщику X с приоритетом urgent, тон —
настойчивый, потому что stock_critical_low"). Формулировка конкретного
текста письма — отдельный шаг, не когнитивный, а генеративный.

```python
"""nowa_body/motor_adapter.py"""

from dataclasses import dataclass
from typing import Any, Dict, Optional
from .mcp_capability import MCPCapability, CapabilityRisk


@dataclass
class ProposedAction:
    """
    То, что Motor Adapter строит из ActionIntent агента,
    ДО прохождения через approval gate.
    """
    action_id: str
    agent_id: str
    tool_id: str
    tool_params: Dict[str, Any]
    risk_level: CapabilityRisk
    intent_summary: str          # человекочитаемое "почему агент это предлагает"
    affective_context: Dict[str, float]  # snapshot valence/arousal/cortisol на момент решения
    estimated_cost_impact: Optional[float] = None
    requires_approval: bool = True


class MotorAdapter:
    """
    Конвертирует ActionIntent агента в конкретный MCP tool call
    и маршрутизирует через ApprovalGate (раздел 6) прежде чем
    когда-либо реально выполниться.

    НИКОГДА не вызывает MCP tool напрямую в обход ApprovalGate —
    это архитектурный инвариант, а не опция.
    """

    def __init__(self, tool_registry, approval_gate, nlg_formatter=None):
        self.tool_registry = tool_registry
        self.approval_gate = approval_gate
        self.nlg_formatter = nlg_formatter  # опционально: LLM для текста писем

    def realize(self, action_intent: Any, agent_state_snapshot: dict) -> ProposedAction:
        """
        1. Маппинг ActionIntent.action_type → конкретный tool_id
           (через RealizationMemory-подобный механизм — какой инструмент
           агент "научился" использовать для какого намерения)
        2. Построение tool_params из ActionIntent.parameters
        3. Если нужен текст (email/сообщение) — вызов nlg_formatter
           с параметрами тона/срочности из ActionIntent, НЕ с решением
           что писать
        4. Возврат ProposedAction — ещё НЕ выполненного действия
        """
        capability = self._resolve_capability(action_intent)
        tool_params = self._build_params(action_intent, capability)

        if capability.risk_level != CapabilityRisk.READ_ONLY and self.nlg_formatter:
            tool_params = self._attach_generated_text(
                action_intent, tool_params
            )

        return ProposedAction(
            action_id=self._generate_action_id(),
            agent_id=action_intent.agent_id,
            tool_id=capability.tool_id,
            tool_params=tool_params,
            risk_level=capability.risk_level,
            intent_summary=self._summarize_intent(action_intent, agent_state_snapshot),
            affective_context=agent_state_snapshot,
            estimated_cost_impact=self._estimate_cost(action_intent, tool_params),
            requires_approval=capability.requires_approval,
        )

    def submit(self, proposed: ProposedAction) -> Any:
        """
        Единственная точка входа для реального выполнения.
        Всегда идёт через approval_gate, который либо:
        - выполняет немедленно (READ_ONLY, или разрешённая автономия)
        - помещает в очередь на одобрение (иначе)
        """
        return self.approval_gate.route(proposed)

    def _resolve_capability(self, action_intent: Any) -> MCPCapability:
        raise NotImplementedError("доменная реализация под роль")

    def _build_params(self, action_intent: Any, capability: MCPCapability) -> dict:
        raise NotImplementedError("доменная реализация под роль")

    def _attach_generated_text(self, action_intent: Any, params: dict) -> dict:
        """
        NLG вызывается ТОЛЬКО для формулировки, не для решений.
        Промпт включает: intent, tone, urgency, factual_constraints —
        всё уже решено агентом, LLM только облекает в слова.
        """
        raise NotImplementedError("доменная реализация под роль")

    def _summarize_intent(self, action_intent: Any, snapshot: dict) -> str:
        raise NotImplementedError

    def _estimate_cost(self, action_intent: Any, params: dict) -> Optional[float]:
        raise NotImplementedError

    def _generate_action_id(self) -> str:
        import uuid
        return str(uuid.uuid4())
```

---

## 5. Stage 1 — Песочница (аналог эволюционного проекта с шиншиллами)

### 5.1 Концепция

Прежде чем агент увидит реальные MCP-данные, он должен прожить
множество виртуальных "кварталов" в симулированном мире закупок —
ровно так же, как эволюционная популяция NOWA (`SwarmEnvironment`,
`EcologyLayer`, `MortalitySystem`, `ReproductiveSystem`, `FitnessEvaluator`)
живёт в симулированной физической среде.

**Прямое переиспользование существующей архитектуры:**

| Эволюционный проект | Procurement Sandbox |
|---|---|
| `SwarmEnvironment` | `ProcurementWorld` |
| `EcologyLayer` (ресурсы) | `MarketSimulator` (спрос/цены/поставщики) |
| `MortalitySystem` (смерть агента) | `BankruptcySystem` (компания банкротится при провале) |
| `ReproductiveSystem` | не нужен на этом этапе (один агент, не популяция) |
| `FitnessEvaluator` (7 критериев) | `ProcurementFitnessEvaluator` (свои критерии) |
| `PopulationObserver` | `SandboxObserver` |

### 5.2 `ProcurementWorld` — симулированная среда

```python
"""nowa_sandbox/procurement_world.py"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import random


@dataclass
class VirtualSupplier:
    supplier_id: str
    reliability: float          # [0,1] — вероятность вовремя доставить
    base_price_multiplier: float
    price_volatility: float     # стандартное отклонение цены между заказами
    lead_time_days: int
    reputation: float = 0.5     # растёт/падает от истории взаимодействий


@dataclass
class VirtualProduct:
    product_id: str
    base_demand_per_day: float
    demand_volatility: float
    holding_cost_per_unit: float
    stockout_penalty_per_unit: float
    current_stock: float = 0.0
    reorder_point: float = 0.0


@dataclass
class ProcurementWorldConfig:
    initial_budget: float = 100_000.0
    n_products: int = 10
    n_suppliers: int = 5
    days_per_quarter: int = 90
    demand_shock_probability: float = 0.05  # редкие резкие скачки спроса
    supplier_default_probability: float = 0.02  # поставщик может "исчезнуть"


class ProcurementWorld:
    """
    Симулированный рынок закупок. Аналог SwarmEnvironment,
    но без множества агентов — здесь один агент живёт в мире
    множества виртуальных сущностей (поставщики, товары, спрос).

    Среда пассивна в том же смысле, что и ValidationEnvironment
    из Warriner-демо: она не управляет агентом, только:
    - выдаёт наблюдения (сток, цены, спрос) через MCP-подобный интерфейс
    - принимает действия агента (заказ у поставщика X на Y единиц)
    - обновляет своё внутреннее состояние (день сменился, спрос реализовался)
    """

    def __init__(self, config: ProcurementWorldConfig, rng: Optional[random.Random] = None):
        self.config = config
        self.rng = rng or random.Random()
        self.day = 0
        self.budget = config.initial_budget
        self.products: Dict[str, VirtualProduct] = self._init_products()
        self.suppliers: Dict[str, VirtualSupplier] = self._init_suppliers()
        self.pending_orders: List[dict] = []
        self.history: List[dict] = []
        self.bankrupt = False

    def _init_products(self) -> Dict[str, VirtualProduct]:
        products = {}
        for i in range(self.config.n_products):
            pid = f"product_{i:03d}"
            products[pid] = VirtualProduct(
                product_id=pid,
                base_demand_per_day=self.rng.uniform(5, 50),
                demand_volatility=self.rng.uniform(0.1, 0.4),
                holding_cost_per_unit=self.rng.uniform(0.5, 2.0),
                stockout_penalty_per_unit=self.rng.uniform(5, 20),
                current_stock=self.rng.uniform(100, 500),
                reorder_point=self.rng.uniform(50, 150),
            )
        return products

    def _init_suppliers(self) -> Dict[str, VirtualSupplier]:
        suppliers = {}
        for i in range(self.config.n_suppliers):
            sid = f"supplier_{i:03d}"
            suppliers[sid] = VirtualSupplier(
                supplier_id=sid,
                reliability=self.rng.uniform(0.7, 0.99),
                base_price_multiplier=self.rng.uniform(0.85, 1.15),
                price_volatility=self.rng.uniform(0.02, 0.15),
                lead_time_days=self.rng.randint(3, 21),
            )
        return suppliers

    # --- Sensory interface (агент "видит" через это) ---

    def observe_stock_levels(self) -> dict:
        return {
            pid: {"quantity": p.current_stock, "reorder_point": p.reorder_point}
            for pid, p in self.products.items()
        }

    def observe_supplier_quote(self, supplier_id: str, product_id: str, qty: float) -> dict:
        supplier = self.suppliers[supplier_id]
        noise = self.rng.gauss(1.0, supplier.price_volatility)
        price = max(0.01, supplier.base_price_multiplier * noise)
        return {
            "supplier_id": supplier_id,
            "product_id": product_id,
            "unit_price": price,
            "lead_time_days": supplier.lead_time_days,
            "reliability_score": supplier.reliability,
            "supplier_is_new": supplier.reputation < 0.3,
        }

    def observe_budget_status(self) -> dict:
        return {"allocated": self.config.initial_budget, "spent": self.config.initial_budget - self.budget}

    # --- Motor interface (агент "действует" через это) ---

    def place_order(self, supplier_id: str, product_id: str, qty: float) -> dict:
        """Аналог MCP tool call create_purchase_order — возвращает результат."""
        quote = self.observe_supplier_quote(supplier_id, product_id, qty)
        total_cost = quote["unit_price"] * qty
        if total_cost > self.budget:
            return {"status": "rejected", "reason": "insufficient_budget"}

        self.budget -= total_cost
        self.pending_orders.append({
            "supplier_id": supplier_id,
            "product_id": product_id,
            "qty": qty,
            "arrival_day": self.day + quote["lead_time_days"],
            "cost": total_cost,
        })
        return {"status": "accepted", "cost": total_cost, "eta_days": quote["lead_time_days"]}

    # --- World tick (независим от агента, как физика) ---

    def tick(self) -> dict:
        """
        Один день симуляции. Вызывается извне (тренировочным циклом),
        НЕ агентом — среда живёт своей жизнью, агент только наблюдает
        и действует, как и положено суверенному агенту в среде.
        """
        self.day += 1
        events = []

        # Реализация спроса
        for pid, product in self.products.items():
            shock = 1.0
            if self.rng.random() < self.config.demand_shock_probability:
                shock = self.rng.uniform(1.5, 3.0)
            demand = max(0.0, self.rng.gauss(
                product.base_demand_per_day * shock,
                product.base_demand_per_day * product.demand_volatility,
            ))
            if product.current_stock < demand:
                shortfall = demand - product.current_stock
                events.append({"type": "stockout", "product_id": pid, "shortfall": shortfall})
                product.current_stock = 0.0
            else:
                product.current_stock -= demand

        # Прибытие заказов
        arrived = [o for o in self.pending_orders if o["arrival_day"] <= self.day]
        self.pending_orders = [o for o in self.pending_orders if o["arrival_day"] > self.day]
        for order in arrived:
            self.products[order["product_id"]].current_stock += order["qty"]
            events.append({"type": "order_arrived", **order})

        # Случайный дефолт поставщика (редкое, но обучающее событие)
        for sid, supplier in self.suppliers.items():
            if self.rng.random() < self.config.supplier_default_probability:
                events.append({"type": "supplier_defaulted", "supplier_id": sid})

        # Банкротство
        if self.budget <= 0:
            self.bankrupt = True
            events.append({"type": "bankruptcy"})

        self.history.append({"day": self.day, "budget": self.budget, "events": events})
        return {"day": self.day, "events": events, "budget": self.budget, "bankrupt": self.bankrupt}
```

### 5.3 `ProcurementFitnessEvaluator` — критерии успеха в песочнице

```python
"""nowa_sandbox/procurement_fitness.py"""

from dataclasses import dataclass


PROCUREMENT_CRITERIA = [
    "cost_efficiency",        # средняя цена vs рыночная медиана
    "stockout_avoidance",     # доля дней без дефицита
    "budget_discipline",      # не приближался к banktrupcy
    "supplier_diversification",  # не зависит от одного поставщика
    "decision_consistency",   # похожие ситуации → похожие решения (не хаотичен)
    "reaction_to_risk_events",  # адекватно реагирует на supplier_defaulted и т.п.
]


@dataclass
class ProcurementFitnessVector:
    cost_efficiency: float
    stockout_avoidance: float
    budget_discipline: float
    supplier_diversification: float
    decision_consistency: float
    reaction_to_risk_events: float
    agent_id: str
    quarter: int


class ProcurementFitnessEvaluator:
    """
    Аналог FitnessEvaluator из эволюционного проекта, но для одного
    агента (не популяции) — оценивает качество работы за квартал
    симуляции песочницы.

    Используется как:
    1. Критерий "агент готов к Stage 2" (супервизия на реальных данных)
    2. Сигнал для итеративной настройки affective_gain / neuromodulator
       параметров агента перед переходом на реальные данные
    """

    def evaluate(self, world_history: list, agent_decision_log: list) -> ProcurementFitnessVector:
        raise NotImplementedError(
            "реализация метрик на основе world.history + agent decisions"
        )

    def graduation_criteria(self, vector: ProcurementFitnessVector) -> dict:
        """
        Пороги для перехода на Stage 2. Все должны быть выполнены.
        """
        thresholds = {
            "cost_efficiency": 0.6,
            "stockout_avoidance": 0.85,
            "budget_discipline": 0.95,  # почти никогда не приближался к банкротству
            "supplier_diversification": 0.4,
            "decision_consistency": 0.6,
            "reaction_to_risk_events": 0.5,
        }
        results = {}
        for criterion, threshold in thresholds.items():
            value = getattr(vector, criterion)
            results[criterion] = {
                "value": value,
                "threshold": threshold,
                "passed": value >= threshold,
            }
        results["all_passed"] = all(r["passed"] for r in results.values())
        return results
```

### 5.4 Тренировочный цикл песочницы

```python
"""nowa_sandbox/training_loop.py — концептуальный псевдокод"""

def run_sandbox_training(
    agent,
    world: "ProcurementWorld",
    encoder: "BusinessEventEncoder",
    n_quarters: int = 20,
    sleep_every_n_days: int = 7,
):
    """
    Аналог SwarmEnvironment.run_generation(), но для одного агента.

    Каждый день:
    1. Агент наблюдает мир (observe_stock_levels, observe_budget_status)
       → encoder строит context_events
    2. agent.step(context_events) → возможен ActionIntent (заказ)
    3. Если ActionIntent — world.place_order(...) немедленно
       (в песочнице approval gate ОТКЛЮЧЕН — учимся быстро,
       без риска реальных денег)
    4. world.tick() — день сменяется, реализуется спрос, приходят заказы
    5. Результат tick() → снова через encoder → feedback агенту (reward)

    Каждые sleep_every_n_days:
        agent.sleep_manager.sleep_cycle() — консолидация

    Каждые n_quarters:
        fitness_evaluator.evaluate(...) → graduation_criteria(...)
        Если all_passed → агент готов к Stage 2
    """
    raise NotImplementedError("детальная реализация в следующей итерации спецификации")
```

### 5.5 Критерии выпуска из песочницы (обязательны все)

| Критерий | Порог | Обоснование |
|---|---|---|
| `cost_efficiency ≥ 0.6` | Закупает не сильно дороже рынка | Базовая экономическая компетентность |
| `stockout_avoidance ≥ 0.85` | Редко допускает дефицит | Операционная надёжность |
| `budget_discipline ≥ 0.95` | Почти никогда не близок к банкротству | **Критично** — это репетиция реального риска |
| `supplier_diversification ≥ 0.4` | Не зависит от одного поставщика | Устойчивость к supplier_defaulted |
| `decision_consistency ≥ 0.6` | Похожие ситуации → похожие решения | Не хаотичен, предсказуем для человека |
| `reaction_to_risk_events ≥ 0.5` | Адекватно реагирует на шоки | Готовность к нештатным ситуациям |
| Минимум 20 симулированных кварталов | — | Достаточно опыта для стабильного гиппокампа |

---

## 6. Stage 2 — Супервизия на реальных данных

### 6.1 Что меняется по сравнению с песочницей

```
Песочница:          world.place_order() → мгновенное исполнение
Супервизия:          MotorAdapter.submit() → ApprovalGate → очередь → человек
```

Агент теперь **читает реальные MCP-данные** (1С остатки, реальные цены
поставщиков), но **любое write-действие** идёт в очередь на одобрение.
READ_ONLY инструменты работают свободно с первого дня Stage 2 — иначе
агент не сможет ничего наблюдать.

### 6.2 `ApprovalGate`

```python
"""nowa_governance/approval_gate.py"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import time


class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"     # человек изменил параметры перед одобрением
    EXPIRED = "expired"       # истёк таймаут ожидания


@dataclass
class ApprovalRecord:
    proposed_action: Any        # ProposedAction из Motor Adapter
    status: ApprovalStatus
    submitted_at: float
    decided_at: Optional[float] = None
    decided_by: Optional[str] = None
    rejection_reason: Optional[str] = None
    modification_diff: Optional[Dict[str, Any]] = None
    executed: bool = False
    execution_result: Optional[Any] = None


class ApprovalGate:
    """
    ЕДИНСТВЕННАЯ точка, через которую write-действия могут достичь
    реального внешнего мира. Никогда не обходится, даже для "мелких"
    действий на Stage 2 — вся автономия разблокируется только на Stage 3,
    и то выборочно per-capability (раздел 7).

    Это архитектурный аналог BasalGanglia Gate внутри мозга NOWA —
    только здесь это внешний, недоступный для когнитивного контроля
    агента барьер.
    """

    def __init__(
        self,
        mcp_executor: Callable[[str, dict], Any],
        notification_channel: Optional[Callable[[ApprovalRecord], None]] = None,
        approval_timeout_hours: float = 48.0,
    ):
        self.mcp_executor = mcp_executor
        self.notification_channel = notification_channel
        self.approval_timeout_hours = approval_timeout_hours
        self.pending_queue: Dict[str, ApprovalRecord] = {}
        self.decided_log: List[ApprovalRecord] = []

    def route(self, proposed_action: Any) -> ApprovalRecord:
        if not proposed_action.requires_approval:
            # Только READ_ONLY на Stage 2. HIGH_WRITE/IRREVERSIBLE
            # НИКОГДА не имеют requires_approval=False на этом этапе —
            # это должно быть архитектурно невозможно, см. раздел 6.3
            return self._execute_immediately(proposed_action)

        record = ApprovalRecord(
            proposed_action=proposed_action,
            status=ApprovalStatus.PENDING,
            submitted_at=time.time(),
        )
        self.pending_queue[proposed_action.action_id] = record
        if self.notification_channel:
            self.notification_channel(record)
        return record

    def decide(
        self,
        action_id: str,
        decision: ApprovalStatus,
        decided_by: str,
        rejection_reason: Optional[str] = None,
        modified_params: Optional[Dict[str, Any]] = None,
    ) -> ApprovalRecord:
        """
        Вызывается человеком через UI/Slack/email при одобрении/отклонении.
        Критически важно: rejection_reason сохраняется структурированно —
        это становится feedback signal для reward агента (раздел 6.4).
        """
        record = self.pending_queue.pop(action_id, None)
        if record is None:
            raise KeyError(f"No pending action with id {action_id}")

        record.status = decision
        record.decided_at = time.time()
        record.decided_by = decided_by
        record.rejection_reason = rejection_reason

        if decision == ApprovalStatus.MODIFIED and modified_params:
            record.modification_diff = modified_params
            record.proposed_action.tool_params.update(modified_params)

        if decision in (ApprovalStatus.APPROVED, ApprovalStatus.MODIFIED):
            record.execution_result = self.mcp_executor(
                record.proposed_action.tool_id,
                record.proposed_action.tool_params,
            )
            record.executed = True

        self.decided_log.append(record)
        return record

    def _execute_immediately(self, proposed_action: Any) -> ApprovalRecord:
        result = self.mcp_executor(proposed_action.tool_id, proposed_action.tool_params)
        record = ApprovalRecord(
            proposed_action=proposed_action,
            status=ApprovalStatus.APPROVED,
            submitted_at=time.time(),
            decided_at=time.time(),
            decided_by="system:read_only_auto",
            executed=True,
            execution_result=result,
        )
        self.decided_log.append(record)
        return record

    def expire_stale(self) -> List[ApprovalRecord]:
        """Вызывается периодически — истёкшие запросы не исполняются."""
        now = time.time()
        expired = []
        for action_id, record in list(self.pending_queue.items()):
            age_hours = (now - record.submitted_at) / 3600.0
            if age_hours > self.approval_timeout_hours:
                record.status = ApprovalStatus.EXPIRED
                expired.append(record)
                del self.pending_queue[action_id]
                self.decided_log.append(record)
        return expired
```

### 6.3 Жёсткое ограничение (не обсуждается на уровне кода агента)

```python
# nowa_governance/hard_constraints.py

class HardConstraintViolation(Exception):
    pass


def assert_stage2_invariant(capability: "MCPCapability") -> None:
    """
    Вызывается ApprovalGate при каждом route(). Это не 'бизнес-правило',
    это защита от бага/prompt injection/эмерджентного поведения агента,
    которая живёт ВНЕ когнитивного контура и не может быть обойдена
    решением агента, даже если агент 'решил' что это правильно.
    """
    from .mcp_capability import CapabilityRisk
    if capability.risk_level in (
        CapabilityRisk.HIGH_WRITE,
        CapabilityRisk.IRREVERSIBLE,
    ):
        if not capability.requires_approval:
            raise HardConstraintViolation(
                f"Capability {capability.tool_id} с риском {capability.risk_level} "
                f"не может иметь requires_approval=False на Stage 2. "
                f"Это архитектурная защита, не подлежит переопределению "
                f"конфигурацией агента."
            )
```

### 6.4 Feedback loop: approval-решение человека → reward агента

Это ключевой механизм обучения на Stage 2 — без него агент не может
улучшаться, а только накапливать эпизоды без корректировки.

```python
"""nowa_governance/feedback_loop.py"""

def approval_to_reward(record: "ApprovalRecord") -> float:
    """
    Конвертирует решение человека в reward signal для NOWA agent,
    аналогично тому, как feedback_rating конвертируется в reward
    в GUI NOWA (submit_feedback → apply_feedback_to_last_experience).
    """
    from .approval_gate import ApprovalStatus

    if record.status == ApprovalStatus.APPROVED:
        return 1.0
    if record.status == ApprovalStatus.MODIFIED:
        # Частичный reward — агент был близок, но не точен
        return 0.4
    if record.status == ApprovalStatus.REJECTED:
        return -1.0
    if record.status == ApprovalStatus.EXPIRED:
        # Не reject, но и не success — агент не создал достаточно
        # срочности/ясности для быстрого решения человека
        return -0.2
    return 0.0


def apply_feedback_to_agent(agent: Any, record: "ApprovalRecord") -> None:
    """
    Записывает feedback в hippocampus агента как reinforcement,
    аналогично apply_feedback_to_last_experience в существующем NOWA GUI.

    rejection_reason (если есть) должен быть сохранён как metadata
    эпизода — это позволяет во время сна проанализировать паттерны
    отклонений (например, 'агент систематически недооценивает
    репутационный риск новых поставщиков').
    """
    reward = approval_to_reward(record)
    context = record.proposed_action.intent_summary
    # Использует существующий hippocampus.reinforce() /
    # value_layer.update() pipeline — не новый механизм
    raise NotImplementedError("привязка к конкретному Agent API")
```

### 6.5 Метрики готовности к Stage 3 (per-capability, не глобально)

Ключевое отличие от Stage 1→2 перехода: разблокировка автономии
происходит **по каждому типу действия отдельно**, не разом для всего агента.

```python
"""nowa_governance/autonomy_readiness.py"""

from dataclasses import dataclass


@dataclass
class CapabilityAutonomyReadiness:
    tool_id: str
    n_decisions: int
    approval_rate: float          # доля APPROVED без изменений
    modification_rate: float
    rejection_rate: float
    avg_decision_latency_hours: float
    max_observed_cost_impact: float

    def is_ready_for_autonomy(
        self,
        min_decisions: int = 30,
        min_approval_rate: float = 0.90,
        max_rejection_rate: float = 0.05,
        max_cost_for_autonomy: float = 500.0,
    ) -> bool:
        return (
            self.n_decisions >= min_decisions
            and self.approval_rate >= min_approval_rate
            and self.rejection_rate <= max_rejection_rate
            and self.max_observed_cost_impact <= max_cost_for_autonomy
        )
```

---

## 7. Stage 3 — Автономия (гранулярная, не бинарная)

### 7.1 Принцип: автономия — свойство capability, не агента

Неверно: "агент переведён в автономный режим".
Верно: "заказы до $500 у поставщиков с reputation > 0.7 выполняются
автономно; всё остальное — по-прежнему через approval gate".

```python
"""nowa_governance/autonomy_policy.py"""

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class AutonomyGrant:
    tool_id: str
    granted_by: str
    granted_at: float
    condition: Callable[[dict], bool]  # доп. условие поверх max_autonomous_value
    max_value: float
    revocable: bool = True
    spot_check_probability: float = 0.10  # даже автономные действия иногда
                                            # выборочно проверяются постфактум


class AutonomyPolicyEngine:
    """
    Проверяется ApprovalGate.route() ПЕРЕД тем, как решить,
    исполнять немедленно или ставить в очередь.
    """

    def __init__(self):
        self.grants: dict = {}

    def grant(self, autonomy_grant: AutonomyGrant) -> None:
        self.grants[autonomy_grant.tool_id] = autonomy_grant

    def revoke(self, tool_id: str) -> None:
        self.grants.pop(tool_id, None)

    def is_autonomous(self, proposed_action: Any) -> bool:
        grant = self.grants.get(proposed_action.tool_id)
        if grant is None:
            return False
        if proposed_action.estimated_cost_impact and (
            proposed_action.estimated_cost_impact > grant.max_value
        ):
            return False
        return grant.condition(proposed_action.tool_params)
```

### 7.2 Обязательные ограничители даже в автономном режиме

| Ограничитель | Значение | Обоснование |
|---|---|---|
| Kill switch | Человек может мгновенно отозвать все `AutonomyGrant` | Аварийная остановка |
| Budget ceiling | Жёсткий лимит трат в день/неделю, вне контроля агента | Защита от runaway spending |
| Spot check | 10% автономных действий выборочно проверяются постфактум | Обнаружение дрейфа поведения |
| Audit log | Каждое действие — неизменяемая запись (кто/что/когда/почему) | Юридическая и операционная прозрачность |
| Periodic re-certification | `AutonomyGrant` истекает через N дней, требует пере-подтверждения | Не "разрешил навсегда и забыл" |

---

## 8. Многоагентная организация (следующий шаг после первого сотрудника)

Согласно принципу суверенности агента (раздел 0, п.1): несколько
виртуальных сотрудников — это несколько независимых NOWA-экземпляров,
**не разделяющих память**. Взаимодействие между ними идёт **через тот же
MCP body layer**, что и с внешним миром — например, через общий Slack-канал
или общие записи в ERP, а не через прямой вызов методов друг друга.

```
Agent "Закупщик"  ──MCP: post_message──▶  Slack #procurement
Agent "Бухгалтер" ──MCP: read_messages──▶  Slack #procurement
```

Это архитектурно правильно: агент-бухгалтер узнаёт о решении закупщика
тем же способом, каким узнал бы человек-коллега — через коммуникацию,
а не через телепатию shared state.

---

## 9. Roadmap

```
Фаза 0 (сейчас):     Архитектурная спецификация (этот документ)

Фаза 1 (2-3 недели): Универсальный Body Layer
                      - MCPCapability, MCPToolRegistry, risk classifier
                      - BusinessEventEncoder (generic)
                      - MotorAdapter (generic) + ApprovalGate

Фаза 2 (3-4 недели): ProcurementWorld песочница
                      - Полная реализация world/fitness/training_loop
                      - Первый агент "Закупщик" живёт 20+ виртуальных кварталов
                      - Достигает graduation_criteria

Фаза 3 (2-3 недели): MCP-подключение к 1С (или тестовой ERP)
                      - Реальный MCPToolRegistry.register_from_mcp_discovery
                      - event_classifier для реальных данных 1С
                      - READ_ONLY доступ включён

Фаза 4 (4-8 недель):  Stage 2 — супервизия
                       - ApprovalGate + notification (Slack/email/UI)
                       - Сбор feedback, накопление reward
                       - Мониторинг CapabilityAutonomyReadiness per tool

Фаза 5 (после Stage 2 метрик): Stage 3 — гранулярная автономия
                       - AutonomyGrant по отдельным capability
                       - Kill switch, budget ceiling, spot check, audit

Фаза 6 (далее):       Второй сотрудник (продажи / бухгалтерия)
                       - Переиспользование Body Layer (универсальность окупается)
                       - Multi-agent коммуникация через MCP (раздел 8)
```

---

## 10. Что нужно от вас для детализации следующих разделов

Этот документ — архитектурный каркас. Для перехода к реализации
потребуется детализация (по аналогии с Warriner-спецификацией — модули,
тест-кейсы, ограничения) для каждой фазы отдельно. Рекомендуемый порядок:

1. **Сначала Фаза 2** (ProcurementWorld) — она не требует реального MCP
   и может быть полностью реализована и провалидирована уже сейчас,
   аналогично Warriner-демо.
2. Пока песочница обучается — параллельно можно прорабатывать Фазу 1
   (Body Layer) как чистую архитектуру без привязки к 1С.
3. Фаза 3 (реальный MCP) — только когда есть на чём тестировать
   (тестовая база 1С или её эмуляция).

Готов написать детальную спецификацию для `ProcurementWorld` +
`ProcurementFitnessEvaluator` + training loop с полными тест-кейсами —
это следующий логичный шаг, аналогичный по глубине Warriner-документу.

---

*Версия 1.0. Архитектурный каркас для проекта "Виртуальные сотрудники NOWA".
Детализация модулей — по мере готовности каждой фазы.*

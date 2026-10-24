## Abstract

Russian version: [NOWA_Virtual_Employees_Architecture_Spec.ru.md](NOWA_Virtual_Employees_Architecture_Spec.ru.md)

This architecture specification defines a company of independent NOWA instances for which MCP tools are organs of a body, not calls visible to the cognitive core. The inherited principles keep the agent's sovereignty, consolidation exclusively in `sleep_cycle`, selection of an intention without the core generating text, and the obligatory path from basal ganglia to the thalamic gate. A principle particular to this line separates money from valence: budget and the approval gate lie outside the cognitive contour, on a par with the physics of an external refusal. An organ is described by an `MCPCapability` record with a risk level from read-only to irreversible write. A heuristic on the tool name only proposes a class and requires human confirmation before access is granted, especially for a high or irreversible write. The sensory encoder turns a call outcome into context tokens and an affective impulse according to a map of business events. In the procurement map given here, critically low stock has valence −0.7 and arousal 0.8, a budget exceeded has −0.8 and 0.7, and a favourable close has 0.8 and 0.6.

Introduction is divided into three stages. Stage 1 is the sandbox: one agent lives through quarters of a simulated market before contact with real data. The configuration sketch in this document sets a budget of 100,000, ten products, five suppliers, a quarter of ninety days, and a demand-shock probability of 0.05; order execution in the sandbox is immediate. Stage 2 reads real MCP data, leaves reading free from the first day, and routes every write through an `ApprovalGate` with statuses of pending, approved, rejected, modified by a person, and expired. Stage 3 makes autonomy a property of a single capability, not of a mode of the whole agent. The policy example in the text is that orders up to $500 with suppliers whose reputation is above 0.7 may execute without a queue when the grant's further condition holds; a later spot check is set at a share of 10%; an instantaneous revocation of all grants, a budget ceiling outside the agent's will, an immutable log, and expiry of a grant with reconfirmation are retained.

Several employees are defined as several instances that do not share memory; their interaction goes through the same external world. A multi-agent organisation is assigned to the step after the first employee. The document thereby separates the sandbox training contour from the later protocol body, in which a write passes the gate and the core remains a component that does not import the protocol.

---

# NOWA Virtual Employees — Architecture Specification

**Version:** 1.0
**Status:** Foundational architecture — requires elaboration by module
**Purpose:** An autonomous company of independent NOWA agents that interact
with the external world through MCP as the "body" of a cognitive "brain"

---

## 0. Inherited principles (not subject to revision)

These principles were established in previous NOWA specifications and remain in force:

1. **The agent is a sovereign unit.** There is no central controller. Each
   virtual employee is an independent NOWA instance with its own hippocampus,
   affective space, neuromodulators, and genome.
2. **Learning occurs only in sleep.** `sleep_manager.sleep_cycle()` is the sole
   mechanism of consolidation. During the working day (waking) the agent does not change weights.
   Since #13: waking outcomes go to the labile tier, stable values change only in `Agent.sleep()`; the employee host passes `dt` ([issue-13-demo-virtual-company.en.md](../../../Docs/specs/issue-13-demo-virtual-company.en.md)).
3. **NOWA does not generate text.** It selects from `RealizationExperience`,
   or makes a decision about an *intention*. The formulation of text is a separate layer
   (see section 4).
4. **BasalGanglia → Thalamic Gate is obligatory.** Every action of the agent passes
   through a Go/NoGo decision before it becomes an `ActionIntent`.

### A new principle for this project

5. **Money is not the same thing as valence.** Financial constraints
   (the budget, approval gates) lie **outside** the agent's cognitive contour —
   this is not part of the brain; it is part of the physical reality of the body, like gravity.
   The agent cannot "change its mind" about a budget limit by force of will — just as it
   cannot change its mind about the physics of an MCP call that returns error 403.

---

## 1. Conceptual model: body and brain

```
                    ┌─────────────────────────────┐
                    │      HUMAN CONTROL           │
                    │  (approval gate, kill switch, │
                    │   budget ceiling, audit)       │
                    └──────────────┬────────────────┘
                                   │ cannot be bypassed
                    ┌──────────────▼────────────────┐
                    │  EXTERNAL WORLD (MCP servers)  │
                    │  1C / ERP / email / Slack /     │
                    │  supplier API / calendar /      │
                    │  payment gateway                │
                    └──────────────┬────────────────┘
                                   │
        ┌──────────────────────────▼──────────────────────────┐
        │              BODY (Body Layer — new)                  │
        │  ┌────────────────┐         ┌────────────────────┐    │
        │  │ Sensory Adapter │         │  Motor Adapter       │   │
        │  │ MCP result →     │         │  ActionIntent →      │   │
        │  │ context_events + │         │  MCP tool call +     │   │
        │  │ affective impulse│         │  approval routing    │   │
        │  └────────┬─────────┘         └──────────▲──────────┘   │
        └───────────┼───────────────────────────────┼──────────────┘
                     │                               │
        ┌────────────▼───────────────────────────────┴──────────────┐
        │           BRAIN (NOWA Agent — core unchanged)               │
        │  hippocampus → affective_space → selector →                  │
        │  BG/Thalamic Gate → ActionIntent                              │
        │  (sleep_manager consolidates the day's experience at night)  │
        └────────────────────────────────────────────────────────────┘
```

**Key metaphor:** MCP tools are not an API; they are sense organs and muscles.
An email tool is not "an integration with mail"; it is "a hand that can write
a letter". The agent does not know what "MCP" is — it knows that it can "inspect
stock on hand" and "write to a supplier". The MCP abstraction is hidden
entirely inside the Sensory/Motor Adapter.

---

## 2. Universal MCP Body Layer

### 2.1 Why universality matters from the first day

If the adapter is bound rigidly to 1C, each new employee (a salesperson,
an accountant, HR) will require the body–brain layer to be rewritten from scratch. Instead,
a declarative model is required: "which sense organs and muscles are available to this
particular agent" is described by configuration, not by code.

### 2.2 `MCPCapability` — a universal description of one MCP tool

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

### 2.3 `MCPToolRegistry` — the registry of organs available to an agent

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

### 2.4 Heuristics of automatic risk classification (for universality)

When a new MCP server is connected (1C, then a CRM, then anything else),
a heuristic is required for a first classification without manual labelling of every tool:

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

## 3. Sensory Adapter — an MCP result → an affective impulse

### 3.1 Principle (inherited from the Warriner demonstration)

Just as `WordStimulusEncoder` converted a word into `context_events`,
here `BusinessEventEncoder` converts the result of an MCP call into
`context_events` plus an affective signal along the same path — **activation
of the hippocampus**, not a direct injection.

### 3.2 `ToolAffectiveMapping` — a configurable map from event to affect

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

### 3.4 Domain event classifier (an example for procurement)

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

### 4.1 Separating "decide" from "formulate"

As stated in principle 3 (section 0): NOWA decides an **intention**
(`ActionIntent`: "write to supplier X with priority urgent, tone —
insistent, because stock_critical_low"). Formulation of the concrete
text of the letter is a separate generative step, outside the cognitive core.

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

## 5. Stage 1 — Sandbox (the analogue of the evolutionary project with chinchillas)

### 5.1 Concept

Before the agent sees real MCP data, it must live through
many virtual "quarters" in a simulated procurement world —
in the same way that an evolutionary population of NOWA (`SwarmEnvironment`,
`EcologyLayer`, `MortalitySystem`, `ReproductiveSystem`, `FitnessEvaluator`)
lives in a simulated physical environment.

**Direct reuse of the existing architecture:**

| Evolutionary project | Procurement Sandbox |
|---|---|
| `SwarmEnvironment` | `ProcurementWorld` |
| `EcologyLayer` (resources) | `MarketSimulator` (demand/prices/suppliers) |
| `MortalitySystem` (death of the agent) | `BankruptcySystem` (the company goes bankrupt on failure) |
| `ReproductiveSystem` | not required at this stage (one agent, not a population) |
| `FitnessEvaluator` (7 criteria) | `ProcurementFitnessEvaluator` (its own criteria) |
| `PopulationObserver` | `SandboxObserver` |

### 5.2 `ProcurementWorld` — a simulated environment

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

### 5.3 `ProcurementFitnessEvaluator` — criteria of success in the sandbox

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

### 5.4 Sandbox training loop

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

### 5.5 Criteria for graduation from the sandbox (all are obligatory)

| Criterion | Threshold | Rationale |
|---|---|---|
| `cost_efficiency ≥ 0.6` | Purchases not much above the market | Basic economic competence |
| `stockout_avoidance ≥ 0.85` | Rarely permits a shortage | Operational reliability |
| `budget_discipline ≥ 0.95` | Almost never close to bankruptcy | **Critical** — this is a rehearsal of real risk |
| `supplier_diversification ≥ 0.4` | Does not depend on a single supplier | Resilience to supplier_defaulted |
| `decision_consistency ≥ 0.6` | Similar situations → similar decisions | Not chaotic; predictable for a person |
| `reaction_to_risk_events ≥ 0.5` | Responds adequately to shocks | Readiness for abnormal situations |
| A minimum of 20 simulated quarters | — | Enough experience for a stable hippocampus |

---

## 6. Stage 2 — Supervision on real data

### 6.1 What changes relative to the sandbox

```
Sandbox:             world.place_order() → immediate execution
Supervision:         MotorAdapter.submit() → ApprovalGate → queue → a person
```

The agent now **reads real MCP data** (1C stock levels, real prices
of suppliers), but **every write action** goes into the approval queue.
READ_ONLY tools operate freely from the first day of Stage 2 — otherwise
the agent would be unable to observe anything.

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

### 6.3 A hard constraint (not open to discussion at the level of the agent's code)

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

### 6.4 Feedback loop: a person's approval decision → the agent's reward

This is the key learning mechanism of Stage 2 — without it the agent cannot
improve, and can only accumulate episodes without correction.

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

### 6.5 Readiness metrics for Stage 3 (per capability, not globally)

The key difference from the transition Stage 1→2: autonomy is unlocked
**for each type of action separately**, not all at once for the whole agent.

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

## 7. Stage 3 — Autonomy (granular, not binary)

### 7.1 Principle: autonomy is a property of a capability, not of the agent

Incorrect: "the agent has been placed in autonomous mode".
Correct: "orders up to $500 with suppliers whose reputation > 0.7 are executed
autonomously; everything else still passes through the approval gate".

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

### 7.2 Obligatory limiters even in autonomous mode

| Limiter | Value | Rationale |
|---|---|---|
| Kill switch | A person can instantaneously revoke every `AutonomyGrant` | Emergency stop |
| Budget ceiling | A hard limit on spending per day or week, outside the agent's control | Protection against runaway spending |
| Spot check | 10% of autonomous actions are checked selectively after the fact | Detection of behavioural drift |
| Audit log | Every action is an immutable record (who/what/when/why) | Legal and operational transparency |
| Periodic re-certification | An `AutonomyGrant` expires after N days and requires reconfirmation | It is not "granted forever and forgotten" |

---

## 8. Multi-agent organisation (the next step after the first employee)

By the principle of the agent's sovereignty (section 0, item 1): several
virtual employees are several independent NOWA instances
**that do not share memory**. Interaction among them proceeds **through the same
MCP body layer** as interaction with the external world — for example, through a shared Slack channel
or shared records in an ERP, and not through a direct call of one another's methods.

```
Agent "Purchaser"   ──MCP: post_message──▶  Slack #procurement
Agent "Accountant"  ──MCP: read_messages──▶  Slack #procurement
```

This is architecturally correct: the accountant agent learns of the purchaser's decision
in the same way a human colleague would — through communication,
and not through the telepathy of shared state.

---

## 9. Roadmap

```
Phase 0 (now):       Architecture specification (this document)

Phase 1 (2–3 weeks): Universal Body Layer
                      - MCPCapability, MCPToolRegistry, risk classifier
                      - BusinessEventEncoder (generic)
                      - MotorAdapter (generic) + ApprovalGate

Phase 2 (3–4 weeks): ProcurementWorld sandbox
                      - Full implementation of world/fitness/training_loop
                      - The first agent, "Purchaser", lives through 20+ virtual quarters
                      - Reaches graduation_criteria

Phase 3 (2–3 weeks): MCP connection to 1C (or a test ERP)
                      - A real MCPToolRegistry.register_from_mcp_discovery
                      - event_classifier for real 1C data
                      - READ_ONLY access is enabled

Phase 4 (4–8 weeks):  Stage 2 — supervision
                       - ApprovalGate + notification (Slack/email/UI)
                       - Collection of feedback, accumulation of reward
                       - Monitoring of CapabilityAutonomyReadiness per tool

Phase 5 (after the Stage 2 metrics): Stage 3 — granular autonomy
                       - An AutonomyGrant for individual capabilities
                       - Kill switch, budget ceiling, spot check, audit

Phase 6 (thereafter): A second employee (sales / accounting)
                       - Reuse of the Body Layer (universality pays for itself)
                       - Multi-agent communication through MCP (section 8)
```

---

## 10. What is required in order to elaborate the following sections

This document is an architectural frame. Proceeding to implementation
requires elaboration (by analogy with the Warriner specification — modules,
test cases, constraints) for each phase separately. The recommended order is:

1. **Phase 2 first** (ProcurementWorld) — it does not require a real MCP
   and can be fully implemented and validated now,
   by analogy with the Warriner demonstration.
2. While the sandbox is being trained, Phase 1
   (the Body Layer) can be developed in parallel as a pure architecture, without a binding to 1C.
3. Phase 3 (a real MCP) — only when there is something on which to test
   (a test 1C database, or an emulation of one).

A detailed specification can next be written for `ProcurementWorld` +
`ProcurementFitnessEvaluator` + the training loop, with complete test cases —
that is the next logical step, analogous in depth to the Warriner document.

---

*Version 1.0. An architectural frame for the project "NOWA Virtual Employees".
Elaboration of the modules proceeds as each phase becomes ready.*

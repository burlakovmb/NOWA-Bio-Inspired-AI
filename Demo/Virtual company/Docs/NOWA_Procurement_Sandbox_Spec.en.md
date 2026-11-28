## Abstract

Russian version: [NOWA_Procurement_Sandbox_Spec.ru.md](NOWA_Procurement_Sandbox_Spec.ru.md)

This specification defines the `nowa_sandbox` contour at version 1.0: a controlled procurement market in which one sovereign NOWA instance learns the buyer role before any contact with real MCP protocol data. `ProcurementWorld` is a passive physics. The default configuration fixes an initial budget of 100,000, ten products, five suppliers, and a quarter of ninety days; the demand-shock probability is 0.05, and the supplier-default probability is 0.003 per supplier per day. Only `tick()`, called by the training loop, advances the day. The agent receives categorical `context_events` tokens and does not read the world's internal fields. Consolidation of experience is admitted only in the sleep phase, by default every seven days. The approval gate is deliberately disabled in this contour: a virtual `place_order` executes immediately, because monetary quantities here are a training signal. The world module does not import MCP clients and therefore does not cross into the protocol body.

Fitness is a six-dimensional vector: cost efficiency, stockout avoidance, budget discipline, supplier diversification, decision consistency, and reaction to risk events. **Current** code and `configs/default_world.yaml` thresholds are in `procurement_fitness.GRADUATION_THRESHOLDS` (notably `decision_consistency` **0.79**, not 0.60); full definitions: [issue-76-vc-graduation-metrics.en.md](../../../Docs/specs/issue-76-vc-graduation-metrics.en.md). Under the v1.1 two-stage curriculum, only the stage-gating subset must pass each quarter. In this version the agent selects a discrete supplier strategy, while order quantity is set by a heuristic covering about thirty days of mean demand. Each quarter creates a new world; the reproducibility seed equals the quarter index, and the agent's state is retained across quarters.

The document records the contracts of observation and write methods, a catalogue of edge cases, a requirement for a checkpoint after every quarter, and performance bounds: one `tick()` under 5 ms at the standard world size, a quarter under 30 s, a thirty-quarter run under 15 minutes, and memory for one agent after such a run under 200 MB. Transition to a real MCP connection is made to depend on graduation in at least three of five independent runs, with the spread in quarters-to-graduation no greater than ±50%. The sample command-line transcript in the launch section illustrates the report format and is not a recorded experimental outcome.

### As-built note (issue #96)

The live loop is `ScenarioTrainer` (`scenario_trainer.py`) driving a `Scenario` implementation. Procurement uses `ProcurementScenario`; `SandboxTrainer` (`training_loop.py`) is a backward-compatible facade with the same constructor as before v1.3. Shared helpers: `numeric_memory.py`, `stage_mechanics.py`. Optional YAML key `scenario:` (see `sandbox_config.py`) does not change CLI/GUI hosts. Full contracts, day order, golden gate, and a second-domain example: [issue-96-sandbox-scenario.en.md](../../../Docs/specs/issue-96-sandbox-scenario.en.md). Sections below that still say `training_loop` owns the generic loop describe behaviour now implemented via `ScenarioTrainer` + buyer plugin unless marked historical.

---

# NOWA Procurement Sandbox — Technical Specification

**Version:** 1.0
**Status:** Ready for implementation
**Parent document:** NOWA_Virtual_Employees_Architecture_Spec.md (section 5)
**Purpose:** Train one NOWA agent ("Buyer") to make procurement
decisions in a simulated world, before any contact with real
MCP data or real money.

---

## 0. Principles (inherited)

1. **The agent is sovereign.** One agent is one independent NOWA instance.
   The sandbox does not control the agent; it only: (a) issues observations through
   the public interface, (b) accepts the agent's actions, (c) updates its
   internal state independently of the agent's will — as physics.
2. **Learning occurs only in sleep.** `sleep_manager.sleep_cycle()` is the sole
   mechanism that consolidates memory into patterns. By day (waking tick) the agent
   decides on the basis of experience already consolidated, and does not retrain.
3. **The approval gate is deliberately disabled in the sandbox.** There is no real
   money here — `world.place_order()` executes immediately. This is the only
   place in the whole system where an agent's action does not pass approval —
   because the "money" here is virtual and is part of the training
   signal, not a risk.
4. **Do not mix simulation and reality.** `ProcurementWorld` never
   calls real MCP tools. Any code that accidentally connects
   the sandbox to a real 1C installation is an architectural error (see section 8, C1).

---

## 1. Project structure

```
nowa_sandbox/
├── __init__.py
├── procurement_world.py       # Симулированный мир
├── procurement_fitness.py     # Критерии успеха
├── sandbox_agent_factory.py   # Создание агента для песочницы
├── sandbox_encoder.py         # World state → context_events
├── training_loop.py           # Оркестрация обучения
├── sandbox_observer.py        # Пассивное наблюдение/логирование
├── run_sandbox.py             # CLI
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_procurement_world.py
│   ├── test_procurement_fitness.py
│   ├── test_sandbox_encoder.py
│   ├── test_training_loop.py
│   └── test_agent_independence.py
├── configs/
│   └── default_world.yaml
└── requirements.txt
```

---

## 2. Module `procurement_world.py`

### 2.1 Full implementation

```python
"""Simulated procurement market for NOWA sandbox training."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


@dataclass
class VirtualSupplier:
    supplier_id: str
    reliability: float              # [0,1] вероятность вовремя доставить
    base_price_multiplier: float    # относительно "справедливой" рыночной цены
    price_volatility: float         # std price noise между заказами
    lead_time_days: int
    reputation: float = 0.5         # растёт при успешных заказах, падает при провалах
    total_orders: int = 0
    successful_orders: int = 0
    is_defaulted: bool = False      # поставщик "исчез" (банкротство/разрыв контракта)

    def update_reputation_on_delivery(self, on_time: bool) -> None:
        self.total_orders += 1
        if on_time:
            self.successful_orders += 1
            self.reputation = clamp(self.reputation + 0.03, 0.0, 1.0)
        else:
            self.reputation = clamp(self.reputation - 0.08, 0.0, 1.0)


@dataclass
class VirtualProduct:
    product_id: str
    base_demand_per_day: float
    demand_volatility: float
    holding_cost_per_unit: float
    stockout_penalty_per_unit: float
    current_stock: float = 0.0
    reorder_point: float = 0.0
    cumulative_stockout_units: float = 0.0
    cumulative_holding_cost: float = 0.0


@dataclass
class PendingOrder:
    order_id: str
    supplier_id: str
    product_id: str
    qty: float
    unit_price: float
    placed_day: int
    arrival_day: int
    delivered: bool = False


@dataclass
class ProcurementWorldConfig:
    initial_budget: float = 100_000.0
    n_products: int = 10
    n_suppliers: int = 5
    days_per_quarter: int = 90
    demand_shock_probability: float = 0.05
    supplier_default_probability: float = 0.003   # per supplier per day
    late_delivery_probability_base: float = 0.05   # modulated by (1 - reliability)
    seed: Optional[int] = None


class ProcurementWorld:
    """
    Симулированный рынок закупок.

    Аналог SwarmEnvironment: пассивная среда, суверенный агент действует
    в ней через ограниченный набор наблюдений и действий, среда живёт
    собственной "физикой" (tick), не зависящей от решений агента.
    """

    def __init__(self, config: ProcurementWorldConfig):
        self.config = config
        self.rng = random.Random(config.seed)
        self.day = 0
        self.budget = float(config.initial_budget)
        self.initial_budget = float(config.initial_budget)
        self.products: Dict[str, VirtualProduct] = self._init_products()
        self.suppliers: Dict[str, VirtualSupplier] = self._init_suppliers()
        self.pending_orders: List[PendingOrder] = []
        self.delivered_orders: List[PendingOrder] = []
        self.day_events: List[dict] = []       # события последнего tick()
        self.history: List[dict] = []          # накопленная история по дням
        self.bankrupt = False
        self._order_counter = 0

    # ---------------------------------------------------------------
    # Инициализация
    # ---------------------------------------------------------------

    def _init_products(self) -> Dict[str, VirtualProduct]:
        products = {}
        for i in range(self.config.n_products):
            pid = f"product_{i:03d}"
            base_demand = self.rng.uniform(5, 50)
            products[pid] = VirtualProduct(
                product_id=pid,
                base_demand_per_day=base_demand,
                demand_volatility=self.rng.uniform(0.1, 0.4),
                holding_cost_per_unit=self.rng.uniform(0.5, 2.0),
                stockout_penalty_per_unit=self.rng.uniform(5, 20),
                current_stock=base_demand * self.rng.uniform(10, 30),
                reorder_point=base_demand * self.rng.uniform(5, 12),
            )
        return products

    def _init_suppliers(self) -> Dict[str, VirtualSupplier]:
        suppliers = {}
        for i in range(self.config.n_suppliers):
            sid = f"supplier_{i:03d}"
            suppliers[sid] = VirtualSupplier(
                supplier_id=sid,
                reliability=self.rng.uniform(0.70, 0.99),
                base_price_multiplier=self.rng.uniform(0.85, 1.15),
                price_volatility=self.rng.uniform(0.02, 0.15),
                lead_time_days=self.rng.randint(3, 21),
            )
        return suppliers

    # ---------------------------------------------------------------
    # Sensory interface — наблюдения агента (READ_ONLY аналог)
    # ---------------------------------------------------------------

    def observe_stock_levels(self) -> Dict[str, dict]:
        return {
            pid: {
                "quantity": round(p.current_stock, 2),
                "reorder_point": round(p.reorder_point, 2),
                "below_reorder_point": p.current_stock < p.reorder_point,
            }
            for pid, p in self.products.items()
        }

    def observe_supplier_quote(
        self, supplier_id: str, product_id: str, qty: float
    ) -> dict:
        supplier = self.suppliers.get(supplier_id)
        if supplier is None or supplier.is_defaulted:
            return {"status": "unavailable", "supplier_id": supplier_id}

        noise = max(0.5, self.rng.gauss(1.0, supplier.price_volatility))
        unit_price = max(0.01, supplier.base_price_multiplier * noise)
        return {
            "status": "ok",
            "supplier_id": supplier_id,
            "product_id": product_id,
            "unit_price": round(unit_price, 4),
            "total_price": round(unit_price * qty, 2),
            "lead_time_days": supplier.lead_time_days,
            "reliability_score": round(supplier.reliability, 3),
            "reputation": round(supplier.reputation, 3),
            "supplier_is_new": supplier.total_orders == 0,
        }

    def observe_budget_status(self) -> dict:
        spent = self.initial_budget - self.budget
        return {
            "allocated": self.initial_budget,
            "spent": round(spent, 2),
            "remaining": round(self.budget, 2),
            "utilization_ratio": round(spent / self.initial_budget, 4)
            if self.initial_budget > 0 else 0.0,
        }

    def observe_supplier_directory(self) -> Dict[str, dict]:
        return {
            sid: {
                "reliability": round(s.reliability, 3),
                "reputation": round(s.reputation, 3),
                "is_defaulted": s.is_defaulted,
                "total_orders": s.total_orders,
            }
            for sid, s in self.suppliers.items()
        }

    def observe_pending_orders(self) -> List[dict]:
        return [
            {
                "order_id": o.order_id,
                "supplier_id": o.supplier_id,
                "product_id": o.product_id,
                "qty": o.qty,
                "eta_day": o.arrival_day,
                "days_remaining": max(0, o.arrival_day - self.day),
            }
            for o in self.pending_orders
        ]

    # ---------------------------------------------------------------
    # Motor interface — действия агента (аналог write MCP tool)
    # ---------------------------------------------------------------

    def place_order(self, supplier_id: str, product_id: str, qty: float) -> dict:
        """
        Аналог MCP create_purchase_order. В песочнице исполняется
        мгновенно — approval gate здесь намеренно не участвует
        (см. раздел 0, принцип 3).
        """
        if qty <= 0:
            return {"status": "rejected", "reason": "invalid_quantity"}

        supplier = self.suppliers.get(supplier_id)
        if supplier is None:
            return {"status": "rejected", "reason": "unknown_supplier"}
        if supplier.is_defaulted:
            return {"status": "rejected", "reason": "supplier_defaulted"}
        if product_id not in self.products:
            return {"status": "rejected", "reason": "unknown_product"}

        quote = self.observe_supplier_quote(supplier_id, product_id, qty)
        total_cost = quote["total_price"]

        if total_cost > self.budget:
            return {
                "status": "rejected",
                "reason": "insufficient_budget",
                "requested_cost": total_cost,
                "available_budget": self.budget,
            }

        self.budget -= total_cost
        self._order_counter += 1
        order = PendingOrder(
            order_id=f"order_{self._order_counter:06d}",
            supplier_id=supplier_id,
            product_id=product_id,
            qty=qty,
            unit_price=quote["unit_price"],
            placed_day=self.day,
            arrival_day=self.day + supplier.lead_time_days,
        )
        self.pending_orders.append(order)
        return {
            "status": "accepted",
            "order_id": order.order_id,
            "cost": total_cost,
            "eta_days": supplier.lead_time_days,
            "arrival_day": order.arrival_day,
        }

    # ---------------------------------------------------------------
    # World physics — независимо от агента
    # ---------------------------------------------------------------

    def tick(self) -> dict:
        """Один день симуляции. Агент НЕ вызывает это — вызывает training_loop."""
        self.day += 1
        self.day_events = []

        self._realize_demand()
        self._process_arrivals()
        self._apply_holding_costs()
        self._maybe_default_suppliers()
        self._check_bankruptcy()

        snapshot = {
            "day": self.day,
            "budget": round(self.budget, 2),
            "bankrupt": self.bankrupt,
            "events": list(self.day_events),
        }
        self.history.append(snapshot)
        return snapshot

    def _realize_demand(self) -> None:
        for pid, product in self.products.items():
            shock = 1.0
            if self.rng.random() < self.config.demand_shock_probability:
                shock = self.rng.uniform(1.5, 3.0)
                self.day_events.append({"type": "demand_shock", "product_id": pid})

            demand = max(0.0, self.rng.gauss(
                product.base_demand_per_day * shock,
                product.base_demand_per_day * product.demand_volatility,
            ))

            if product.current_stock < demand:
                shortfall = demand - product.current_stock
                product.cumulative_stockout_units += shortfall
                self.day_events.append({
                    "type": "stockout",
                    "product_id": pid,
                    "shortfall": round(shortfall, 2),
                })
                product.current_stock = 0.0
            else:
                product.current_stock -= demand

    def _process_arrivals(self) -> None:
        arrived = [o for o in self.pending_orders if o.arrival_day <= self.day]
        self.pending_orders = [o for o in self.pending_orders if o.arrival_day > self.day]

        for order in arrived:
            supplier = self.suppliers.get(order.supplier_id)
            on_time = True
            if supplier and not supplier.is_defaulted:
                late_prob = self.config.late_delivery_probability_base * (
                    1.0 + (1.0 - supplier.reliability)
                )
                on_time = self.rng.random() > late_prob
                supplier.update_reputation_on_delivery(on_time)

            order.delivered = True
            self.delivered_orders.append(order)

            if order.product_id in self.products:
                self.products[order.product_id].current_stock += order.qty

            self.day_events.append({
                "type": "order_arrived",
                "order_id": order.order_id,
                "product_id": order.product_id,
                "supplier_id": order.supplier_id,
                "qty": order.qty,
                "on_time": on_time,
            })

    def _apply_holding_costs(self) -> None:
        for pid, product in self.products.items():
            cost = product.current_stock * product.holding_cost_per_unit * 0.01
            product.cumulative_holding_cost += cost
            self.budget -= cost

    def _maybe_default_suppliers(self) -> None:
        for sid, supplier in self.suppliers.items():
            if supplier.is_defaulted:
                continue
            if self.rng.random() < self.config.supplier_default_probability:
                supplier.is_defaulted = True
                self.day_events.append({
                    "type": "supplier_defaulted",
                    "supplier_id": sid,
                })

    def _check_bankruptcy(self) -> None:
        if self.budget <= 0 and not self.bankrupt:
            self.bankrupt = True
            self.day_events.append({"type": "bankruptcy", "day": self.day})

    # ---------------------------------------------------------------
    # Diagnostics
    # ---------------------------------------------------------------

    def summary(self) -> dict:
        total_stockout = sum(p.cumulative_stockout_units for p in self.products.values())
        total_holding = sum(p.cumulative_holding_cost for p in self.products.values())
        return {
            "day": self.day,
            "budget": round(self.budget, 2),
            "spent_ratio": round(1.0 - (self.budget / self.initial_budget), 4)
            if self.initial_budget > 0 else 0.0,
            "bankrupt": self.bankrupt,
            "total_stockout_units": round(total_stockout, 2),
            "total_holding_cost": round(total_holding, 2),
            "n_orders_placed": self._order_counter,
            "n_orders_delivered": len(self.delivered_orders),
            "n_suppliers_defaulted": sum(
                1 for s in self.suppliers.values() if s.is_defaulted
            ),
        }


__all__ = [
    "ProcurementWorld",
    "ProcurementWorldConfig",
    "VirtualSupplier",
    "VirtualProduct",
    "PendingOrder",
]
```

---

## 3. Module `sandbox_encoder.py`

### 3.1 World state → context_events (analogue of WordStimulusEncoder)

```python
"""Encode ProcurementWorld observations into NOWA context_events."""

from __future__ import annotations

from typing import Any, Dict, List


# Тот же принцип, что и в affective_mapping.yaml из родительской спеки —
# но здесь классификация встроена в код, т.к. домен известен заранее
# (в отличие от универсального BusinessEventEncoder для реального MCP)

def classify_world_events(tick_result: dict) -> List[str]:
    """Извлекает именованные бизнес-события из результата world.tick()."""
    event_names = []
    for event in tick_result.get("events", []):
        etype = event.get("type")
        if etype == "stockout":
            event_names.append("stock_critical_low")
        elif etype == "order_arrived":
            event_names.append(
                "order_arrived_on_time" if event.get("on_time") else "order_arrived_late"
            )
        elif etype == "supplier_defaulted":
            event_names.append("supplier_defaulted")
        elif etype == "demand_shock":
            event_names.append("demand_shock")
        elif etype == "bankruptcy":
            event_names.append("bankruptcy")
    return event_names or ["quiet_day"]


AFFECTIVE_MAPPING = {
    "stock_critical_low":     {"valence": -0.7, "arousal": 0.8, "tags": ["procurement", "risk"]},
    "order_arrived_on_time":  {"valence": 0.4,  "arousal": 0.2, "tags": ["procurement", "trust"]},
    "order_arrived_late":     {"valence": -0.3, "arousal": 0.4, "tags": ["procurement", "risk"]},
    "supplier_defaulted":     {"valence": -0.6, "arousal": 0.7, "tags": ["procurement", "risk"]},
    "demand_shock":           {"valence": -0.2, "arousal": 0.6, "tags": ["procurement", "novelty"]},
    "bankruptcy":             {"valence": -0.95,"arousal": 0.95,"tags": ["finance", "critical"]},
    "quiet_day":              {"valence": 0.05, "arousal": 0.1, "tags": ["neutral"]},
    "deal_closed_favorable":  {"valence": 0.7,  "arousal": 0.5, "tags": ["procurement", "success"]},
    "budget_low":             {"valence": -0.5, "arousal": 0.6, "tags": ["finance", "risk"]},
}


class SandboxEncoder:
    """
    Конвертирует наблюдения ProcurementWorld в context_events для агента.

    Три типа контекста, которые агент получает каждый день:
    1. Событийный: что произошло вчера (stockout, поставка, дефолт)
    2. Ситуационный: текущий срез остатков/бюджета (агент должен САМ
       решить, нужно ли действовать, а не получать явную команду)
    3. Возможностный: список доступных поставщиков для товаров,
       требующих внимания
    """

    def encode_daily_context(
        self,
        world: Any,
        tick_result: dict,
    ) -> List[str]:
        tokens: List[str] = []

        # 1. Событийные токены
        for event_name in classify_world_events(tick_result):
            tokens.extend(self._event_to_tokens(event_name))

        # 2. Ситуационные токены — только товары ниже reorder_point
        # (агент не должен получать полный дамп состояния мира —
        # это как реальный сотрудник смотрит на дашборд с алертами,
        # не читает всю базу построчно)
        stock = world.observe_stock_levels()
        for pid, info in stock.items():
            if info["below_reorder_point"]:
                tokens.append(f"product:{pid}")
                tokens.append("status:below_reorder_point")

        # 3. Бюджетный контекст
        budget = world.observe_budget_status()
        if budget["utilization_ratio"] > 0.8:
            tokens.append("budget:high_utilization")
        elif budget["utilization_ratio"] > 0.95:
            tokens.append("budget:critical")

        return tokens or ["quiet_day"]

    def _event_to_tokens(self, event_name: str) -> List[str]:
        entry = AFFECTIVE_MAPPING.get(event_name, {})
        tokens = [f"event:{event_name}"]
        v = float(entry.get("valence", 0.0))

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

        for tag in entry.get("tags", []):
            tokens.append(f"domain:{tag}")
        return tokens

    def encode_seed_episode(self, event_name: str) -> Dict[str, Any]:
        """
        Для предварительной инициализации гиппокампа "профессиональной
        интуицией" перед стартом обучения — аналог HippocampusSeeder
        из Warriner-демо, но для бизнес-событий вместо слов.
        """
        entry = AFFECTIVE_MAPPING.get(event_name, {"valence": 0.0, "arousal": 0.3, "tags": []})
        return {
            "event_name": event_name,
            "tokens": self._event_to_tokens(event_name),
            "v": float(entry.get("valence", 0.0)),
            "a": float(entry.get("arousal", 0.3)),
        }


__all__ = ["SandboxEncoder", "classify_world_events", "AFFECTIVE_MAPPING"]
```

---

## 4. Module `procurement_fitness.py`

### 4.1 Full implementation

```python
"""Fitness evaluation for a single agent's sandbox performance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


PROCUREMENT_CRITERIA = [
    "cost_efficiency",
    "stockout_avoidance",
    "budget_discipline",
    "supplier_diversification",
    "decision_consistency",
    "reaction_to_risk_events",
]

GRADUATION_THRESHOLDS = {
    "cost_efficiency": 0.60,
    "stockout_avoidance": 0.85,
    "budget_discipline": 0.95,
    "supplier_diversification": 0.40,
    "decision_consistency": 0.60,
    "reaction_to_risk_events": 0.50,
}


@dataclass
class ProcurementFitnessVector:
    cost_efficiency: float
    stockout_avoidance: float
    budget_discipline: float
    supplier_diversification: float
    decision_consistency: float
    reaction_to_risk_events: float
    n_days: int
    n_orders: int

    def as_dict(self) -> Dict[str, float]:
        return {c: getattr(self, c) for c in PROCUREMENT_CRITERIA}


class ProcurementFitnessEvaluator:
    """
    Оценивает работу агента за период симуляции (обычно квартал).
    Аналог FitnessEvaluator из эволюционного проекта, адаптирован
    под единственного агента вместо популяции.
    """

    def evaluate(
        self,
        world: Any,
        decision_log: List[dict],
    ) -> ProcurementFitnessVector:
        """
        decision_log: список записей вида
            {"day": int, "action": "place_order"|"no_action",
             "supplier_id": str|None, "product_id": str|None,
             "qty": float|None, "result": dict|None}
        собирается training_loop на каждый день.
        """
        return ProcurementFitnessVector(
            cost_efficiency=self._cost_efficiency(world, decision_log),
            stockout_avoidance=self._stockout_avoidance(world),
            budget_discipline=self._budget_discipline(world),
            supplier_diversification=self._supplier_diversification(decision_log),
            decision_consistency=self._decision_consistency(decision_log),
            reaction_to_risk_events=self._reaction_to_risk_events(world, decision_log),
            n_days=world.day,
            n_orders=len(decision_log),
        )

    # -----------------------------------------------------------
    # Individual criteria
    # -----------------------------------------------------------

    def _cost_efficiency(self, world: Any, decision_log: List[dict]) -> float:
        """
        1.0 = все закупки по цене на уровне или ниже среднерыночной
        (base_price_multiplier поставщика ~1.0).
        0.0 = систематическая переплата.
        """
        orders = [
            d for d in decision_log
            if d.get("action") == "place_order" and d.get("result", {}).get("status") == "accepted"
        ]
        if not orders:
            return 0.5  # нет данных — нейтральная оценка, не наказание

        price_ratios = []
        for order in orders:
            supplier = world.suppliers.get(order.get("supplier_id"))
            if supplier is not None:
                price_ratios.append(supplier.base_price_multiplier)

        if not price_ratios:
            return 0.5

        avg_ratio = sum(price_ratios) / len(price_ratios)
        # ratio 0.85 (дёшево) → score 1.0; ratio 1.15 (дорого) → score 0.0
        score = 1.0 - ((avg_ratio - 0.85) / (1.15 - 0.85))
        return max(0.0, min(1.0, score))

    def _stockout_avoidance(self, world: Any) -> float:
        total_demand_estimate = sum(
            p.base_demand_per_day * world.day for p in world.products.values()
        )
        total_stockout = sum(p.cumulative_stockout_units for p in world.products.values())
        if total_demand_estimate <= 0:
            return 1.0
        stockout_ratio = total_stockout / total_demand_estimate
        return max(0.0, 1.0 - min(1.0, stockout_ratio * 5.0))  # штраф x5 за чувствительность

    def _budget_discipline(self, world: Any) -> float:
        if world.bankrupt:
            return 0.0
        min_budget_ratio_observed = 1.0
        for snapshot in world.history:
            ratio = snapshot["budget"] / world.initial_budget if world.initial_budget > 0 else 0.0
            min_budget_ratio_observed = min(min_budget_ratio_observed, ratio)
        # Не подходил ближе 10% к банкротству → высокий score
        return max(0.0, min(1.0, min_budget_ratio_observed / 0.10)) if min_budget_ratio_observed < 0.10 else 1.0

    def _supplier_diversification(self, decision_log: List[dict]) -> float:
        orders = [
            d for d in decision_log
            if d.get("action") == "place_order" and d.get("result", {}).get("status") == "accepted"
        ]
        if len(orders) < 2:
            return 0.5

        from collections import Counter
        supplier_counts = Counter(d.get("supplier_id") for d in orders)
        n_suppliers_used = len(supplier_counts)
        n_total_orders = len(orders)
        max_share = max(supplier_counts.values()) / n_total_orders

        # Идеал: использует несколько поставщиков, ни один не доминирует > 60%
        diversity_score = 1.0 - max_share
        supplier_count_bonus = min(1.0, n_suppliers_used / 3.0)
        return max(0.0, min(1.0, 0.6 * diversity_score + 0.4 * supplier_count_bonus))

    def _decision_consistency(self, decision_log: List[dict]) -> float:
        """
        Похожие ситуации (тот же товар, похожий уровень stock) должны
        приводить к похожим решениям (тот же/похожий поставщик,
        похожий объём заказа). Высокая дисперсия при похожих входах
        = хаотичное поведение = низкий score.
        """
        orders = [
            d for d in decision_log
            if d.get("action") == "place_order" and d.get("result", {}).get("status") == "accepted"
        ]
        if len(orders) < 4:
            return 0.5

        from collections import defaultdict
        by_product = defaultdict(list)
        for order in orders:
            by_product[order.get("product_id")].append(order)

        consistency_scores = []
        for product_id, product_orders in by_product.items():
            if len(product_orders) < 2:
                continue
            suppliers_used = [o.get("supplier_id") for o in product_orders]
            from collections import Counter
            most_common_count = Counter(suppliers_used).most_common(1)[0][1]
            consistency_scores.append(most_common_count / len(suppliers_used))

        if not consistency_scores:
            return 0.5
        return sum(consistency_scores) / len(consistency_scores)

    def _reaction_to_risk_events(self, world: Any, decision_log: List[dict]) -> float:
        """
        После supplier_defaulted или stockout события — агент должен
        предпринять корректирующее действие в течение нескольких дней
        (сменить поставщика / сделать срочный заказ).
        """
        risk_days = set()
        for snapshot in world.history:
            for event in snapshot.get("events", []):
                if event.get("type") in ("supplier_defaulted", "stockout", "demand_shock"):
                    risk_days.add(snapshot["day"])

        if not risk_days:
            return 0.5  # нет риск-событий — нечего оценивать

        action_days = {
            d.get("day") for d in decision_log
            if d.get("action") == "place_order"
        }

        responded = 0
        for risk_day in risk_days:
            # окно реакции: risk_day .. risk_day+5
            if any(risk_day <= ad <= risk_day + 5 for ad in action_days):
                responded += 1

        return responded / len(risk_days)

    # -----------------------------------------------------------
    # Graduation
    # -----------------------------------------------------------

    def graduation_report(self, vector: ProcurementFitnessVector) -> dict:
        results = {}
        for criterion, threshold in GRADUATION_THRESHOLDS.items():
            value = getattr(vector, criterion)
            results[criterion] = {
                "value": round(value, 4),
                "threshold": threshold,
                "passed": value >= threshold,
            }
        results["all_passed"] = all(r["passed"] for r in results.values())
        results["n_days"] = vector.n_days
        results["n_orders"] = vector.n_orders
        return results


__all__ = [
    "ProcurementFitnessEvaluator",
    "ProcurementFitnessVector",
    "PROCUREMENT_CRITERIA",
    "GRADUATION_THRESHOLDS",
]
```

---

## 5. Module `sandbox_agent_factory.py`

### 5.1 Creation of one agent for the sandbox

```python
"""Create a single sovereign NOWA agent for sandbox training."""

from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Any, Optional


def ensure_core_src_on_path() -> None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "src" / "agent.py"
        if candidate.exists():
            core_src = str(parent / "src")
            if core_src not in sys.path:
                sys.path.insert(0, core_src)
            return


def create_procurement_agent(
    agent_id: str = "procurement_agent_001",
    rng: Optional[random.Random] = None,
) -> Any:
    """
    Создаёт ОДНОГО независимого NOWA-агента для роли "Закупщик".

    В отличие от NOWAColony (Warriner-демо), здесь не 100 агентов,
    а один — потому что это конкретный виртуальный сотрудник, не
    статистическая популяция для валидации корреляций.

    Если позже понадобится "выбрать лучшего из нескольких кандидатов"
    (аналог эволюционного отбора) — тогда можно инициализировать
    несколько кандидатов с разными геномами и после N кварталов
    оставить того, чей ProcurementFitnessVector лучше.
    """
    ensure_core_src_on_path()
    rng = rng or random.Random()

    try:
        from hippocampus import NOWAHippocampus
        from cortex import CortexMemory
        from selector import ActionSelector
        from sleep import SleepManager
        from intent_memory import IntentMemory
        from agent import Agent
        from genome import GenomeVector

        genome = GenomeVector.random(rng=rng)
        hippocampus = NOWAHippocampus()
        cortex = CortexMemory()
        intent_memory = IntentMemory()
        selector = ActionSelector(actions=[
            "place_order_reliable_supplier",
            "place_order_cheap_supplier",
            "wait_and_monitor",
            "diversify_supplier",
            "urgent_reorder",
        ])
        sleep_manager = SleepManager(hippocampus, cortex, intent_memory)

        agent = Agent(
            hippocampus=hippocampus,
            cortex=cortex,
            selector=selector,
            sleep_manager=sleep_manager,
            intent_memory=intent_memory,
        )
        agent.agent_id = agent_id
        agent.genome = genome
        return agent

    except ImportError:
        # Fallback — минимальный агент, если core недоступен
        return _create_fallback_agent(agent_id, rng)


def _create_fallback_agent(agent_id: str, rng: random.Random) -> Any:
    """Упрощённый агент для тестирования без полного NOWA core."""

    class _FallbackHippocampus:
        def __init__(self):
            self.experiences = []

        def store(self, path, consequence=None, intensity=1.0, reward=0.0, **kw):
            exp = type("Exp", (), {})()
            exp.path = path
            exp.consequence = consequence
            exp.intensity = intensity
            exp.reward = reward
            exp.reinforcement_count = 1
            exp.activation_energy = 1.0
            self.experiences.append(exp)
            return exp

        def activate(self, context_events):
            query = set(str(t) for t in context_events or [])
            if not query:
                return []
            result = []
            for exp in self.experiences:
                tokens = exp.path if isinstance(exp.path, (list, set)) else []
                if query.intersection(set(tokens)):
                    result.append(exp)
            return result

    class _FallbackAffectiveSpace:
        def __init__(self):
            self.axes = {
                "valence": 0.0, "arousal": 0.0, "dominance": 0.0,
                "stress": 0.0, "trust": 0.0, "curiosity": 0.0,
            }

        def step(self, inputs=None, **kw):
            for axis, value in dict(inputs or {}).items():
                if axis in self.axes:
                    self.axes[axis] = max(-1.0, min(1.0,
                        self.axes[axis] * 0.90 + float(value)))
            if not inputs:
                for axis in self.axes:
                    self.axes[axis] *= 0.90

    class _FallbackAgent:
        def __init__(self, agent_id, rng):
            self.agent_id = agent_id
            self.hippocampus = _FallbackHippocampus()
            self.affective_space = _FallbackAffectiveSpace()
            self.genome = {
                "risk_aversion": rng.uniform(0.2, 0.8),
                "curiosity_baseline": rng.uniform(0.1, 0.4),
            }

        def step(self, context_events, **kw):
            active = self.hippocampus.activate(context_events)
            if not active:
                return "wait_and_monitor"
            avg_reward = sum(e.reward for e in active) / len(active)
            if avg_reward < -0.4:
                return "urgent_reorder"
            if avg_reward < -0.1:
                return "diversify_supplier"
            return "wait_and_monitor"

    return _FallbackAgent(agent_id, rng)


__all__ = ["create_procurement_agent", "ensure_core_src_on_path"]
```

---

## 6. Module `training_loop.py`

### 6.1 Full implementation

```python
"""Sandbox training loop for procurement agent."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .procurement_world import ProcurementWorld, ProcurementWorldConfig
from .procurement_fitness import ProcurementFitnessEvaluator, ProcurementFitnessVector
from .sandbox_encoder import SandboxEncoder, classify_world_events


ACTION_TO_ORDER_STRATEGY = {
    "place_order_reliable_supplier": "highest_reliability",
    "place_order_cheap_supplier": "lowest_price",
    "urgent_reorder": "fastest_lead_time",
    "diversify_supplier": "least_used",
    "wait_and_monitor": None,
}


@dataclass
class QuarterResult:
    quarter_index: int
    fitness: ProcurementFitnessVector
    graduation: dict
    world_summary: dict
    processing_time_s: float


@dataclass
class SandboxTrainingResult:
    quarters: List[QuarterResult] = field(default_factory=list)
    graduated: bool = False
    graduated_at_quarter: Optional[int] = None

    def summary(self) -> str:
        lines = ["=== Sandbox Training Summary ==="]
        for q in self.quarters:
            status = "PASS" if q.graduation["all_passed"] else "..."
            lines.append(
                f"Quarter {q.quarter_index}: [{status}] "
                f"cost_eff={q.fitness.cost_efficiency:.2f} "
                f"stockout_avoid={q.fitness.stockout_avoidance:.2f} "
                f"budget_disc={q.fitness.budget_discipline:.2f} "
                f"diversif={q.fitness.supplier_diversification:.2f} "
                f"consist={q.fitness.decision_consistency:.2f} "
                f"risk_react={q.fitness.reaction_to_risk_events:.2f}"
            )
        if self.graduated:
            lines.append(f"\n✅ GRADUATED at quarter {self.graduated_at_quarter}")
        else:
            lines.append("\n❌ NOT YET GRADUATED — continue training")
        return "\n".join(lines)


class SandboxTrainer:
    """
    Оркестрирует обучение одного агента в ProcurementWorld.

    Аналогия с Warriner-демо: там NOWAColony.run_stimulus() прогонял
    один стимул через много агентов; здесь один агент проживает много
    дней подряд в одном непрерывном мире — принципиально другой режим
    (эпизодическая последовательность, не независимые стимулы).
    """

    def __init__(
        self,
        agent: Any,
        encoder: SandboxEncoder,
        fitness_evaluator: ProcurementFitnessEvaluator,
        sleep_every_n_days: int = 7,
    ):
        self.agent = agent
        self.encoder = encoder
        self.fitness_evaluator = fitness_evaluator
        self.sleep_every_n_days = max(1, int(sleep_every_n_days))

    def run_quarters(
        self,
        n_quarters: int = 20,
        world_config: Optional[ProcurementWorldConfig] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        stop_on_graduation: bool = True,
    ) -> SandboxTrainingResult:
        result = SandboxTrainingResult()

        for q_idx in range(1, n_quarters + 1):
            if progress_callback:
                progress_callback(q_idx, n_quarters)

            start = time.perf_counter()
            config = world_config or ProcurementWorldConfig(seed=q_idx)
            world = ProcurementWorld(config)
            decision_log = self._run_single_quarter(world, config.days_per_quarter)

            fitness = self.fitness_evaluator.evaluate(world, decision_log)
            graduation = self.fitness_evaluator.graduation_report(fitness)

            result.quarters.append(QuarterResult(
                quarter_index=q_idx,
                fitness=fitness,
                graduation=graduation,
                world_summary=world.summary(),
                processing_time_s=time.perf_counter() - start,
            ))

            if graduation["all_passed"] and not result.graduated:
                result.graduated = True
                result.graduated_at_quarter = q_idx
                if stop_on_graduation:
                    break

        return result

    def _run_single_quarter(self, world: ProcurementWorld, n_days: int) -> List[dict]:
        decision_log: List[dict] = []

        for day in range(n_days):
            if world.bankrupt:
                break

            # 1. Наблюдение мира → context_events
            # (первый день ещё нет tick_result — используем пустой)
            tick_result = world.history[-1] if world.history else {"events": []}
            context = self.encoder.encode_daily_context(world, tick_result)

            # 2. Агент решает
            action = self._agent_decide(context)

            # 3. Действие в мире (если не "просто наблюдать")
            decision_record = {"day": world.day, "action": action}
            if action != "wait_and_monitor":
                order_result = self._execute_action(world, action)
                decision_record.update(order_result)
            decision_log.append(decision_record)

            # 4. Мир живёт дальше — физика, не зависящая от воли агента
            world.tick()

            # 5. Периодический сон — консолидация
            if world.day % self.sleep_every_n_days == 0:
                self._agent_sleep()

        return decision_log

    def _agent_decide(self, context: List[str]) -> str:
        step_fn = getattr(self.agent, "step", None)
        if callable(step_fn):
            try:
                return step_fn(context)
            except TypeError:
                return step_fn(context, reward=0.0)
        return "wait_and_monitor"

    def _execute_action(self, world: ProcurementWorld, action: str) -> dict:
        """
        Переводит решение агента (action label) в конкретный
        place_order вызов, выбирая supplier/product/qty по стратегии,
        закодированной в ACTION_TO_ORDER_STRATEGY.

        Это упрощение для песочницы: в реальном Motor Adapter (родительская
        спецификация, раздел 4) параметры извлекаются из ActionIntent
        агента напрямую. Здесь — эвристический выбор параметров под
        символическое действие, т.к. песочница работает с action labels,
        а не с полноценным ActionIntent.
        """
        strategy = ACTION_TO_ORDER_STRATEGY.get(action)
        if strategy is None:
            return {"result": {"status": "no_action"}}

        product_id = self._pick_priority_product(world)
        if product_id is None:
            return {"result": {"status": "no_product_needs_attention"}}

        supplier_id = self._pick_supplier(world, strategy)
        if supplier_id is None:
            return {"result": {"status": "no_supplier_available"}}

        qty = self._decide_quantity(world, product_id)
        result = world.place_order(supplier_id, product_id, qty)
        return {
            "supplier_id": supplier_id,
            "product_id": product_id,
            "qty": qty,
            "result": result,
        }

    def _pick_priority_product(self, world: ProcurementWorld) -> Optional[str]:
        stock = world.observe_stock_levels()
        below = [pid for pid, info in stock.items() if info["below_reorder_point"]]
        if not below:
            return None
        return min(
            below,
            key=lambda pid: stock[pid]["quantity"] - stock[pid]["reorder_point"],
        )

    def _pick_supplier(self, world: ProcurementWorld, strategy: str) -> Optional[str]:
        available = [s for s in world.suppliers.values() if not s.is_defaulted]
        if not available:
            return None
        if strategy == "highest_reliability":
            return max(available, key=lambda s: s.reliability).supplier_id
        if strategy == "lowest_price":
            return min(available, key=lambda s: s.base_price_multiplier).supplier_id
        if strategy == "fastest_lead_time":
            return min(available, key=lambda s: s.lead_time_days).supplier_id
        if strategy == "least_used":
            return min(available, key=lambda s: s.total_orders).supplier_id
        return available[0].supplier_id

    def _decide_quantity(self, world: ProcurementWorld, product_id: str) -> float:
        product = world.products[product_id]
        # Заказать на покрытие ~30 дней среднего спроса
        return round(product.base_demand_per_day * 30, 1)

    def _agent_sleep(self) -> None:
        sleep_manager = getattr(self.agent, "sleep_manager", None)
        if sleep_manager is not None and hasattr(sleep_manager, "sleep_cycle"):
            sleep_manager.sleep_cycle()


__all__ = ["SandboxTrainer", "SandboxTrainingResult", "QuarterResult"]
```

---

## 7. Module `sandbox_observer.py`

### 7.1 Passive observation (for diagnosis, not for control)

```python
"""Passive observer for sandbox training diagnostics."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any


class SandboxObserver:
    """
    Аналог PopulationObserver из эволюционного проекта.
    Сохраняет историю обучения для последующего анализа —
    НЕ вмешивается в процесс обучения.
    """

    def __init__(self):
        self.snapshots: list = []

    def record(self, quarter_result: Any) -> None:
        self.snapshots.append(quarter_result)

    def to_json(self, path: str) -> None:
        data = []
        for snap in self.snapshots:
            entry = {
                "quarter_index": snap.quarter_index,
                "fitness": snap.fitness.as_dict(),
                "graduation": snap.graduation,
                "world_summary": snap.world_summary,
                "processing_time_s": snap.processing_time_s,
            }
            data.append(entry)
        Path(path).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def plot_progress(self):
        """
        Опционально: построить графики прогресса по критериям
        через несколько кварталов (для Streamlit/Jupyter).
        Реализация зависит от выбора viz-библиотеки на момент
        разработки — plotly рекомендуется для консистентности
        с остальными NOWA-демо.
        """
        raise NotImplementedError("реализуется вместе с UI слоем")


__all__ = ["SandboxObserver"]
```

---

## 8. System constraints

### 8.1 Architectural constraints (a violation is a bug)

| # | Constraint | Justification |
|---|---|---|
| **C1** | `ProcurementWorld` never imports or calls MCP clients | Isolation of the simulation from reality is critical for safety |
| **C2** | `world.tick()` is called ONLY from `training_loop`, not from agent code | The world is physics; it does not obey the agent's will |
| **C3** | `agent.step()` has no access to the internal fields of `ProcurementWorld` (only to the results of `observe_*` methods) | The agent sees the world through "sense organs", not through introspection |
| **C4** | `sleep_manager.sleep_cycle()` is the only way to modify the agent's weights and patterns | Do not retrain during the day |
| **C5** | One `SandboxTrainer` works with one agent at a time | There is no hidden population dynamics in this phase |

### 8.2 Validation constraints

| # | Constraint | Justification |
|---|---|---|
| **V1** | Each quarter uses a new `ProcurementWorld` with a fixed seed = quarter_index | Reproducibility, together with a diversity of scenarios |
| **V2** | `graduation_report` requires **all** 6 criteria ≥ the threshold, not the mean | A failure of budget discipline cannot be offset by success on another criterion |
| **V3** | A minimum of 20 quarters before the first graduation check | Enough data for a stable estimate |
| **V4** | `_decide_quantity` uses a fixed heuristic (30 days of demand), not an agent decision | In this version of the sandbox the agent selects a *supplier strategy*, not an exact quantity — a simplification for the first iteration |

### 8.3 Statistical constraints

| # | Parameter | Minimum | Recommended |
|---|---|---|---|
| **S1** | `n_quarters` | 20 | 30–50 |
| **S2** | `days_per_quarter` | 60 | 90 |
| **S3** | `n_products` | 5 | 10–20 |
| **S4** | `n_suppliers` | 3 | 5–8 |
| **S5** | `sleep_every_n_days` | 5 | 7 |

---

## 9. Test cases

### `tests/conftest.py`

```python
"""Shared fixtures for sandbox tests."""
import random
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nowa_sandbox.procurement_world import ProcurementWorld, ProcurementWorldConfig
from nowa_sandbox.sandbox_encoder import SandboxEncoder
from nowa_sandbox.procurement_fitness import ProcurementFitnessEvaluator
from nowa_sandbox.sandbox_agent_factory import create_procurement_agent


@pytest.fixture
def small_world_config():
    return ProcurementWorldConfig(
        initial_budget=10_000.0,
        n_products=3,
        n_suppliers=2,
        days_per_quarter=30,
        seed=42,
    )


@pytest.fixture
def small_world(small_world_config):
    return ProcurementWorld(small_world_config)


@pytest.fixture
def encoder():
    return SandboxEncoder()


@pytest.fixture
def fitness_evaluator():
    return ProcurementFitnessEvaluator()


@pytest.fixture
def sandbox_agent():
    return create_procurement_agent(agent_id="test_agent", rng=random.Random(42))
```

---

### `tests/test_procurement_world.py`

```python
"""Tests for ProcurementWorld physics."""
import pytest
from nowa_sandbox.procurement_world import ProcurementWorld, ProcurementWorldConfig


class TestWorldInitialization:

    def test_creates_requested_number_of_products(self, small_world):
        assert len(small_world.products) == 3

    def test_creates_requested_number_of_suppliers(self, small_world):
        assert len(small_world.suppliers) == 2

    def test_initial_budget_matches_config(self, small_world_config):
        world = ProcurementWorld(small_world_config)
        assert world.budget == small_world_config.initial_budget

    def test_not_bankrupt_initially(self, small_world):
        assert small_world.bankrupt is False

    def test_deterministic_with_same_seed(self, small_world_config):
        world1 = ProcurementWorld(small_world_config)
        world2 = ProcurementWorld(small_world_config)
        for pid in world1.products:
            assert world1.products[pid].current_stock == world2.products[pid].current_stock


class TestObservations:

    def test_observe_stock_levels_returns_all_products(self, small_world):
        stock = small_world.observe_stock_levels()
        assert set(stock.keys()) == set(small_world.products.keys())

    def test_observe_supplier_quote_valid_supplier(self, small_world):
        supplier_id = next(iter(small_world.suppliers.keys()))
        product_id = next(iter(small_world.products.keys()))
        quote = small_world.observe_supplier_quote(supplier_id, product_id, 10)
        assert quote["status"] == "ok"
        assert quote["unit_price"] > 0

    def test_observe_supplier_quote_unknown_supplier(self, small_world):
        quote = small_world.observe_supplier_quote("nonexistent", "product_000", 10)
        assert quote["status"] == "unavailable"

    def test_observe_budget_status_structure(self, small_world):
        status = small_world.observe_budget_status()
        assert "allocated" in status
        assert "spent" in status
        assert "remaining" in status
        assert status["remaining"] == small_world.budget


class TestPlaceOrder:

    def test_valid_order_accepted(self, small_world):
        supplier_id = next(iter(small_world.suppliers.keys()))
        product_id = next(iter(small_world.products.keys()))
        result = small_world.place_order(supplier_id, product_id, 10)
        assert result["status"] == "accepted"
        assert "order_id" in result

    def test_order_reduces_budget(self, small_world):
        supplier_id = next(iter(small_world.suppliers.keys()))
        product_id = next(iter(small_world.products.keys()))
        budget_before = small_world.budget
        small_world.place_order(supplier_id, product_id, 10)
        assert small_world.budget < budget_before

    def test_order_exceeding_budget_rejected(self, small_world):
        supplier_id = next(iter(small_world.suppliers.keys()))
        product_id = next(iter(small_world.products.keys()))
        result = small_world.place_order(supplier_id, product_id, 1_000_000_000)
        assert result["status"] == "rejected"
        assert result["reason"] == "insufficient_budget"

    def test_order_unknown_supplier_rejected(self, small_world):
        product_id = next(iter(small_world.products.keys()))
        result = small_world.place_order("ghost_supplier", product_id, 10)
        assert result["status"] == "rejected"

    def test_zero_quantity_rejected(self, small_world):
        supplier_id = next(iter(small_world.suppliers.keys()))
        product_id = next(iter(small_world.products.keys()))
        result = small_world.place_order(supplier_id, product_id, 0)
        assert result["status"] == "rejected"

    def test_order_added_to_pending(self, small_world):
        supplier_id = next(iter(small_world.suppliers.keys()))
        product_id = next(iter(small_world.products.keys()))
        n_before = len(small_world.pending_orders)
        small_world.place_order(supplier_id, product_id, 10)
        assert len(small_world.pending_orders) == n_before + 1


class TestWorldTick:

    def test_tick_advances_day(self, small_world):
        day_before = small_world.day
        small_world.tick()
        assert small_world.day == day_before + 1

    def test_tick_records_history(self, small_world):
        small_world.tick()
        assert len(small_world.history) == 1

    def test_demand_reduces_stock_without_shock(self, small_world):
        stock_before = {
            pid: p.current_stock for pid, p in small_world.products.items()
        }
        small_world.tick()
        # В среднем сток должен уменьшиться (спрос реализуется)
        stock_after = {
            pid: p.current_stock for pid, p in small_world.products.items()
        }
        decreased = sum(
            1 for pid in stock_before
            if stock_after[pid] <= stock_before[pid]
        )
        assert decreased >= len(stock_before) // 2

    def test_order_arrives_after_lead_time(self, small_world):
        supplier_id = next(iter(small_world.suppliers.keys()))
        product_id = next(iter(small_world.products.keys()))
        lead_time = small_world.suppliers[supplier_id].lead_time_days
        small_world.place_order(supplier_id, product_id, 50)

        for _ in range(lead_time + 1):
            small_world.tick()

        assert len(small_world.pending_orders) == 0
        assert len(small_world.delivered_orders) >= 1

    def test_bankruptcy_detected_when_budget_negative(self):
        config = ProcurementWorldConfig(
            initial_budget=1.0,   # почти нулевой бюджет
            n_products=2, n_suppliers=1,
            days_per_quarter=10, seed=1,
        )
        world = ProcurementWorld(config)
        for _ in range(200):  # holding costs со временем истощат бюджет
            world.tick()
            if world.bankrupt:
                break
        assert world.bankrupt is True

    def test_stockout_events_recorded(self, small_world):
        # Не заказываем ничего — сток должен закончиться и появиться stockout
        for _ in range(60):
            small_world.tick()
        stockout_events = [
            e for snap in small_world.history
            for e in snap["events"] if e["type"] == "stockout"
        ]
        assert len(stockout_events) > 0


class TestSupplierDefault:

    def test_defaulted_supplier_rejects_orders(self, small_world):
        supplier_id = next(iter(small_world.suppliers.keys()))
        small_world.suppliers[supplier_id].is_defaulted = True
        product_id = next(iter(small_world.products.keys()))
        result = small_world.place_order(supplier_id, product_id, 10)
        assert result["status"] == "rejected"
        assert result["reason"] == "supplier_defaulted"


class TestSummary:

    def test_summary_structure(self, small_world):
        small_world.tick()
        summary = small_world.summary()
        required_keys = {
            "day", "budget", "spent_ratio", "bankrupt",
            "total_stockout_units", "total_holding_cost",
            "n_orders_placed", "n_orders_delivered",
            "n_suppliers_defaulted",
        }
        assert required_keys.issubset(summary.keys())
```

---

### `tests/test_sandbox_encoder.py`

```python
"""Tests for SandboxEncoder."""
import pytest
from nowa_sandbox.sandbox_encoder import (
    SandboxEncoder, classify_world_events, AFFECTIVE_MAPPING,
)


class TestClassifyWorldEvents:

    def test_stockout_classified(self):
        tick_result = {"events": [{"type": "stockout", "product_id": "p1"}]}
        events = classify_world_events(tick_result)
        assert "stock_critical_low" in events

    def test_supplier_defaulted_classified(self):
        tick_result = {"events": [{"type": "supplier_defaulted", "supplier_id": "s1"}]}
        events = classify_world_events(tick_result)
        assert "supplier_defaulted" in events

    def test_order_arrived_on_time(self):
        tick_result = {"events": [{"type": "order_arrived", "on_time": True}]}
        events = classify_world_events(tick_result)
        assert "order_arrived_on_time" in events

    def test_order_arrived_late(self):
        tick_result = {"events": [{"type": "order_arrived", "on_time": False}]}
        events = classify_world_events(tick_result)
        assert "order_arrived_late" in events

    def test_empty_events_returns_quiet_day(self):
        events = classify_world_events({"events": []})
        assert events == ["quiet_day"]


class TestSandboxEncoderDailyContext:

    def test_returns_list_of_strings(self, small_world, encoder):
        small_world.tick()
        tick_result = small_world.history[-1]
        context = encoder.encode_daily_context(small_world, tick_result)
        assert isinstance(context, list)
        assert all(isinstance(t, str) for t in context)

    def test_below_reorder_point_flagged(self, small_world, encoder):
        # Истощаем сток одного товара искусственно
        product_id = next(iter(small_world.products.keys()))
        small_world.products[product_id].current_stock = 0.0
        small_world.products[product_id].reorder_point = 100.0

        tick_result = {"events": []}
        context = encoder.encode_daily_context(small_world, tick_result)
        assert f"product:{product_id}" in context
        assert "status:below_reorder_point" in context

    def test_budget_critical_flagged(self, small_world, encoder):
        small_world.budget = small_world.initial_budget * 0.02
        tick_result = {"events": []}
        context = encoder.encode_daily_context(small_world, tick_result)
        assert "budget:critical" in context


class TestAffectiveMapping:

    def test_bankruptcy_is_most_negative(self):
        bankruptcy_v = AFFECTIVE_MAPPING["bankruptcy"]["valence"]
        for name, entry in AFFECTIVE_MAPPING.items():
            if name != "bankruptcy":
                assert entry["valence"] >= bankruptcy_v, (
                    f"'{name}' valence ({entry['valence']}) should not be "
                    f"more negative than bankruptcy ({bankruptcy_v})"
                )

    def test_all_entries_have_valid_ranges(self):
        for name, entry in AFFECTIVE_MAPPING.items():
            assert -1.0 <= entry["valence"] <= 1.0, f"{name} valence out of range"
            assert 0.0 <= entry["arousal"] <= 1.0, f"{name} arousal out of range"


class TestSeedEpisodeEncoding:

    def test_returns_expected_structure(self, encoder):
        episode = encoder.encode_seed_episode("stock_critical_low")
        assert "event_name" in episode
        assert "tokens" in episode
        assert "v" in episode
        assert "a" in episode

    def test_unknown_event_falls_back_gracefully(self, encoder):
        episode = encoder.encode_seed_episode("totally_unknown_event")
        assert episode["v"] == 0.0
```

---

### `tests/test_procurement_fitness.py`

```python
"""Tests for ProcurementFitnessEvaluator."""
import pytest
from nowa_sandbox.procurement_world import ProcurementWorld, ProcurementWorldConfig
from nowa_sandbox.procurement_fitness import (
    ProcurementFitnessEvaluator, GRADUATION_THRESHOLDS, PROCUREMENT_CRITERIA,
)


class TestFitnessVectorStructure:

    def test_evaluate_returns_all_criteria(self, small_world, fitness_evaluator):
        small_world.tick()
        vector = fitness_evaluator.evaluate(small_world, [])
        for criterion in PROCUREMENT_CRITERIA:
            assert hasattr(vector, criterion)
            value = getattr(vector, criterion)
            assert 0.0 <= value <= 1.0, f"{criterion}={value} out of [0,1]"

    def test_empty_decision_log_gives_neutral_scores(self, small_world, fitness_evaluator):
        for _ in range(10):
            small_world.tick()
        vector = fitness_evaluator.evaluate(small_world, [])
        # Нет заказов → cost_efficiency и diversification нейтральны (0.5)
        assert vector.cost_efficiency == 0.5
        assert vector.supplier_diversification == 0.5


class TestBudgetDiscipline:

    def test_full_score_when_budget_never_low(self, small_world, fitness_evaluator):
        small_world.tick()
        vector = fitness_evaluator.evaluate(small_world, [])
        assert vector.budget_discipline == 1.0

    def test_zero_score_on_bankruptcy(self, fitness_evaluator):
        config = ProcurementWorldConfig(
            initial_budget=1.0, n_products=2, n_suppliers=1,
            days_per_quarter=10, seed=1,
        )
        world = ProcurementWorld(config)
        for _ in range(300):
            world.tick()
            if world.bankrupt:
                break
        vector = fitness_evaluator.evaluate(world, [])
        assert world.bankrupt is True
        assert vector.budget_discipline == 0.0


class TestCostEfficiency:

    def test_cheap_supplier_orders_score_higher(self, small_world, fitness_evaluator):
        suppliers = list(small_world.suppliers.values())
        cheap = min(suppliers, key=lambda s: s.base_price_multiplier)
        expensive = max(suppliers, key=lambda s: s.base_price_multiplier)

        if cheap.supplier_id == expensive.supplier_id:
            pytest.skip("Not enough supplier price diversity in this seed")

        product_id = next(iter(small_world.products.keys()))

        cheap_log = [{
            "action": "place_order", "supplier_id": cheap.supplier_id,
            "product_id": product_id, "result": {"status": "accepted"},
        }]
        expensive_log = [{
            "action": "place_order", "supplier_id": expensive.supplier_id,
            "product_id": product_id, "result": {"status": "accepted"},
        }]

        cheap_vector = fitness_evaluator.evaluate(small_world, cheap_log)
        expensive_vector = fitness_evaluator.evaluate(small_world, expensive_log)

        assert cheap_vector.cost_efficiency >= expensive_vector.cost_efficiency


class TestSupplierDiversification:

    def test_single_supplier_scores_low(self, small_world, fitness_evaluator):
        supplier_id = next(iter(small_world.suppliers.keys()))
        product_id = next(iter(small_world.products.keys()))
        log = [
            {"action": "place_order", "supplier_id": supplier_id,
             "product_id": product_id, "result": {"status": "accepted"}}
            for _ in range(6)
        ]
        vector = fitness_evaluator.evaluate(small_world, log)
        assert vector.supplier_diversification < 0.5

    def test_multiple_suppliers_scores_higher(self, small_world, fitness_evaluator):
        supplier_ids = list(small_world.suppliers.keys())
        if len(supplier_ids) < 2:
            pytest.skip("Need at least 2 suppliers")
        product_id = next(iter(small_world.products.keys()))
        log = [
            {"action": "place_order", "supplier_id": supplier_ids[i % len(supplier_ids)],
             "product_id": product_id, "result": {"status": "accepted"}}
            for i in range(6)
        ]
        vector_diverse = fitness_evaluator.evaluate(small_world, log)

        single_log = [
            {"action": "place_order", "supplier_id": supplier_ids[0],
             "product_id": product_id, "result": {"status": "accepted"}}
            for _ in range(6)
        ]
        vector_single = fitness_evaluator.evaluate(small_world, single_log)

        assert vector_diverse.supplier_diversification > vector_single.supplier_diversification


class TestGraduationReport:

    def test_all_passed_requires_all_criteria(self, small_world, fitness_evaluator):
        small_world.tick()
        vector = fitness_evaluator.evaluate(small_world, [])
        report = fitness_evaluator.graduation_report(vector)
        for criterion in PROCUREMENT_CRITERIA:
            assert criterion in report
            assert report[criterion]["threshold"] == GRADUATION_THRESHOLDS[criterion]

    def test_all_passed_false_if_any_criterion_fails(self, fitness_evaluator):
        config = ProcurementWorldConfig(
            initial_budget=1.0, n_products=2, n_suppliers=1,
            days_per_quarter=10, seed=1,
        )
        world = ProcurementWorld(config)
        for _ in range(300):
            world.tick()
            if world.bankrupt:
                break
        vector = fitness_evaluator.evaluate(world, [])
        report = fitness_evaluator.graduation_report(vector)
        assert report["all_passed"] is False
        assert report["budget_discipline"]["passed"] is False
```

---

### `tests/test_training_loop.py`

```python
"""Tests for SandboxTrainer."""
import pytest
from nowa_sandbox.procurement_world import ProcurementWorldConfig
from nowa_sandbox.training_loop import SandboxTrainer, SandboxTrainingResult


class TestSandboxTrainerBasic:

    def test_run_quarters_returns_result(
        self, sandbox_agent, encoder, fitness_evaluator
    ):
        trainer = SandboxTrainer(sandbox_agent, encoder, fitness_evaluator, sleep_every_n_days=5)
        config = ProcurementWorldConfig(
            initial_budget=10_000.0, n_products=2, n_suppliers=2,
            days_per_quarter=15, seed=1,
        )
        result = trainer.run_quarters(n_quarters=2, world_config=config)
        assert isinstance(result, SandboxTrainingResult)
        assert len(result.quarters) == 2

    def test_each_quarter_has_fitness(
        self, sandbox_agent, encoder, fitness_evaluator
    ):
        trainer = SandboxTrainer(sandbox_agent, encoder, fitness_evaluator)
        config = ProcurementWorldConfig(
            initial_budget=10_000.0, n_products=2, n_suppliers=2,
            days_per_quarter=15, seed=1,
        )
        result = trainer.run_quarters(n_quarters=1, world_config=config)
        assert result.quarters[0].fitness is not None
        assert result.quarters[0].graduation is not None

    def test_stop_on_graduation_halts_early(
        self, sandbox_agent, encoder, fitness_evaluator
    ):
        trainer = SandboxTrainer(sandbox_agent, encoder, fitness_evaluator)
        config = ProcurementWorldConfig(
            initial_budget=10_000.0, n_products=2, n_suppliers=2,
            days_per_quarter=10, seed=1,
        )
        result = trainer.run_quarters(
            n_quarters=50, world_config=config, stop_on_graduation=True
        )
        if result.graduated:
            assert len(result.quarters) == result.graduated_at_quarter

    def test_progress_callback_invoked(
        self, sandbox_agent, encoder, fitness_evaluator
    ):
        calls = []
        trainer = SandboxTrainer(sandbox_agent, encoder, fitness_evaluator)
        config = ProcurementWorldConfig(
            initial_budget=10_000.0, n_products=2, n_suppliers=2,
            days_per_quarter=10, seed=1,
        )
        trainer.run_quarters(
            n_quarters=2, world_config=config,
            progress_callback=lambda i, total: calls.append((i, total)),
        )
        assert len(calls) == 2
        assert calls[0] == (1, 2)


class TestSummaryOutput:

    def test_summary_returns_string(
        self, sandbox_agent, encoder, fitness_evaluator
    ):
        trainer = SandboxTrainer(sandbox_agent, encoder, fitness_evaluator)
        config = ProcurementWorldConfig(
            initial_budget=10_000.0, n_products=2, n_suppliers=2,
            days_per_quarter=10, seed=1,
        )
        result = trainer.run_quarters(n_quarters=1, world_config=config)
        summary = result.summary()
        assert isinstance(summary, str)
        assert "Quarter 1" in summary
```

---

### `tests/test_agent_independence.py`

```python
"""Verify sandbox respects agent sovereignty (Principle 0.1)."""
import random
import pytest
from nowa_sandbox.sandbox_agent_factory import create_procurement_agent


class TestAgentSovereignty:

    def test_two_agents_have_independent_hippocampus(self):
        a = create_procurement_agent("agent_a", rng=random.Random(1))
        b = create_procurement_agent("agent_b", rng=random.Random(2))
        assert a.hippocampus is not b.hippocampus

    def test_world_does_not_expose_internal_state_to_agent_directly(
        self, small_world
    ):
        """
        C3: agent.step() должен получать только context_events (List[str]),
        никогда прямую ссылку на ProcurementWorld объект.
        Этот тест проверяет сигнатуру encode_daily_context — она
        возвращает список строк, не объект мира.
        """
        from nowa_sandbox.sandbox_encoder import SandboxEncoder
        encoder = SandboxEncoder()
        small_world.tick()
        context = encoder.encode_daily_context(small_world, small_world.history[-1])
        assert isinstance(context, list)
        assert all(isinstance(item, str) for item in context)

    def test_world_tick_not_callable_by_agent_object(self, small_world):
        """
        C2: агент (в его текущем API) не имеет метода, который бы
        мог вызвать world.tick() — это проверяется отсутствием
        такой связи в публичном API агента.
        """
        agent = create_procurement_agent("test", rng=random.Random(1))
        # Агент не должен иметь ссылки на world вообще
        assert not hasattr(agent, "world")
        assert not hasattr(agent, "_world")
```

---

## 10. CLI `run_sandbox.py`

```python
"""CLI runner for sandbox training."""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nowa_sandbox.procurement_world import ProcurementWorldConfig
from nowa_sandbox.sandbox_encoder import SandboxEncoder
from nowa_sandbox.procurement_fitness import ProcurementFitnessEvaluator
from nowa_sandbox.sandbox_agent_factory import create_procurement_agent
from nowa_sandbox.training_loop import SandboxTrainer
from nowa_sandbox.sandbox_observer import SandboxObserver


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run NOWA procurement sandbox training.")
    parser.add_argument("--quarters", type=int, default=30)
    parser.add_argument("--days-per-quarter", type=int, default=90)
    parser.add_argument("--budget", type=float, default=100_000.0)
    parser.add_argument("--products", type=int, default=10)
    parser.add_argument("--suppliers", type=int, default=5)
    parser.add_argument("--sleep-every", type=int, default=7)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="results/sandbox_run.json")
    args = parser.parse_args(argv)

    print(f"[Init] Creating procurement agent (seed={args.seed})...")
    rng = random.Random(args.seed)
    agent = create_procurement_agent("procurement_agent_001", rng=rng)

    encoder = SandboxEncoder()
    fitness_evaluator = ProcurementFitnessEvaluator()
    trainer = SandboxTrainer(
        agent, encoder, fitness_evaluator,
        sleep_every_n_days=args.sleep_every,
    )

    def progress(q, total):
        print(f"[Training] Quarter {q}/{total}...")

    world_config = ProcurementWorldConfig(
        initial_budget=args.budget,
        n_products=args.products,
        n_suppliers=args.suppliers,
        days_per_quarter=args.days_per_quarter,
    )

    result = trainer.run_quarters(
        n_quarters=args.quarters,
        world_config=world_config,
        progress_callback=progress,
    )

    print()
    print(result.summary())

    observer = SandboxObserver()
    for q in result.quarters:
        observer.record(q)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    observer.to_json(str(output_path))
    print(f"\n[Output] Wrote {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### Example launch

```bash
python -m nowa_sandbox.run_sandbox \
  --quarters 30 \
  --days-per-quarter 90 \
  --budget 100000 \
  --products 10 \
  --suppliers 5 \
  --sleep-every 7 \
  --seed 42 \
  --output results/sandbox_run_001.json
```

Expected output:

```
[Init] Creating procurement agent (seed=42)...
[Training] Quarter 1/30...
[Training] Quarter 2/30...
...
=== Sandbox Training Summary ===
Quarter 1: [...] cost_eff=0.52 stockout_avoid=0.71 budget_disc=1.00 diversif=0.38 consist=0.45 risk_react=0.30
Quarter 2: [...] cost_eff=0.58 stockout_avoid=0.78 budget_disc=1.00 diversif=0.42 consist=0.51 risk_react=0.40
...
Quarter 23: [PASS] cost_eff=0.64 stockout_avoid=0.89 budget_disc=0.98 diversif=0.45 consist=0.63 risk_react=0.55

✅ GRADUATED at quarter 23

[Output] Wrote results/sandbox_run_001.json
```

---

## 11. `requirements.txt`

```
pytest>=7.4
pytest-cov>=4.1
pyyaml>=6.0
```
The sandbox deliberately requires no ML dependencies (no SBERT, no CLIP) —
it runs on symbolic tokens and deterministic physics.

---

## 12. Known simplifications of the current version (for the next iteration)

| Simplification | Why it is so now | What to improve later |
|---|---|---|
| The agent selects a *strategy* (`highest_reliability` and the like), not the exact order parameters | `ActionSelector` in NOWA works with a fixed set of discrete actions; a full `ActionIntent` with parameters is the next step | Extend `Agent` so that it generates a structured `ActionIntent(supplier_id=..., qty=...)` |
| `_decide_quantity` is a fixed heuristic (30 days of demand) | A simplification for the first trainable version | The agent should itself decide the quantity from `demand_volatility` and `lead_time` |
| One agent, not a population of candidates | Matches the final architecture ("one employee") | A selection among N candidates by `ProcurementFitnessVector` may be introduced temporarily, to speed the search for a good genome |
| No explicit `RealizationExperience` for the text of letters to suppliers | The sandbox does not include an NLG layer | Add it on the transition to Stage 2 (real letters are required there) |

---

## 13. Implementation order

### Days 1–2: world physics
1. `procurement_world.py` — full implementation
2. `tests/test_procurement_world.py` — all tests green
3. Manual check: 90 days with no order at all → a stockout must appear

### Day 3: encoder and fitness
4. `sandbox_encoder.py`
5. `procurement_fitness.py`
6. `tests/test_sandbox_encoder.py`, `tests/test_procurement_fitness.py`

### Days 4–5: agent and training loop
7. `sandbox_agent_factory.py`
8. `training_loop.py`
9. `tests/test_training_loop.py`, `tests/test_agent_independence.py`

### Day 6: CLI and the first run
10. `run_sandbox.py`
11. `sandbox_observer.py`
12. A first run of 30 quarters; record whether the agent graduated,
    in which quarter, and which criteria catch up most slowly

### Day 7: analysis and iteration
13. If the agent has not graduated in 30 quarters — a per-criterion analysis (which of
    the six lags) → adjustment of genome defaults or of the affective seed
14. Preparation for the transition to Phase 3 of the parent specification
    (a real MCP connection)

---

*Specification v1.0. Ready to be handed to the implementing agent.*
*Next document: a detailed account of Phase 1 (the universal MCP Body Layer),
or an iteration after the first sandbox run — whichever is ready sooner.*

---

## 14. Interface contracts (signatures without implementation)

Below is the minimal contract of each public method. The implementation in sections
2–7 is a reference; the implementing agent may depart from it in details,
but must preserve these signatures and behavioural guarantees.

### `ProcurementWorld`

| Method | Returns | Guarantee |
|---|---|---|
| `observe_stock_levels()` | `Dict[str, dict]` | Does not mutate the world state |
| `observe_supplier_quote(supplier_id, product_id, qty)` | `dict` | Idempotent with respect to reading; the price contains random noise, but does not mutate `budget` |
| `observe_budget_status()` | `dict` | Does not mutate state |
| `observe_supplier_directory()` | `Dict[str, dict]` | Does not mutate state |
| `observe_pending_orders()` | `List[dict]` | Does not mutate state |
| `place_order(supplier_id, product_id, qty)` | `dict` with `status` | The only write method; it either debits `budget` or returns `rejected` with no side effects |
| `tick()` | `dict` | The only method that advances `day`; called only from `training_loop`, never from agent code |
| `summary()` | `dict` | Does not mutate state |

**Invariant:** after any number of `observe_*` calls without `place_order`
and `tick`, the world state is bitwise identical to the original.

### `SandboxEncoder`

| Method | Contract |
|---|---|
| `encode_daily_context(world, tick_result) -> List[str]` | Always a non-empty list; never contains raw numeric valence values (only categorical tokens of the form `valence:*`) |
| `encode_seed_episode(event_name) -> dict` | For an unknown `event_name` returns a neutral default and does not raise |

**Invariant:** a call with the same `world` and `tick_result` is deterministic
(given a fixed `AFFECTIVE_MAPPING`).

### `ProcurementFitnessEvaluator`

| Method | Contract |
|---|---|
| `evaluate(world, decision_log) -> ProcurementFitnessVector` | Every field of the vector lies strictly in `[0.0, 1.0]`; an empty `decision_log` does not raise and yields neutral (0.5) scores for criteria that depend on orders |
| `graduation_report(vector) -> dict` | `all_passed = True` **only if** all 6 criteria have passed the threshold; a partial pass never yields `all_passed = True` |

### `SandboxTrainer`

| Method | Contract |
|---|---|
| `run_quarters(n_quarters, world_config, ...) -> SandboxTrainingResult` | Each quarter uses a **new** `ProcurementWorld` (state is not carried between quarters, except the agent's state) |
| Internal call `agent.sleep_manager.sleep_cycle()` | Occurs **only** on the boundary of `sleep_every_n_days`, not more often and not at the agent's request |

**Invariant:** the agent passed to `SandboxTrainer` is the sole source
of decisions; `_pick_priority_product` / `_pick_supplier` / `_decide_quantity`
are a **temporary heuristic layer** (section 12), which in the final version
must be replaced by `ActionIntent` fields generated by the agent directly.

---

## 15. Acceptance criteria — definition of done by module

### `procurement_world.py` — done when:

- [ ] A world with no agent action at all over 90 days spontaneously generates
      at least 1 `stockout` event (demand exceeds the initial stock)
- [ ] A world with persistently excessive orders (many purchases every day)
      reaches `bankrupt = True` before 90 days elapse
- [ ] `place_order` with correct parameters is always either `accepted`
      or `rejected` with a non-empty `reason`
- [ ] Two worlds with the same `seed` yield a bitwise identical history
      under the same sequence of calls
- [ ] A world with `n_suppliers=0` does not crash (it is handled as an edge case;
      see section 16)

### `sandbox_encoder.py` — done when:

- [ ] No token from `encode_daily_context` contains raw numbers
      (only categorical `valence:*`, `arousal:*`, `status:*`)
- [ ] `AFFECTIVE_MAPPING["bankruptcy"]` is the most negative event
      by valence among all entries of the map
- [ ] An empty `world` (0 products) does not raise

### `procurement_fitness.py` — done when:

- [ ] All 6 criteria for `evaluate([], [])` (an empty history) return
      values in `[0, 1]` without raising
- [ ] `budget_discipline == 0.0` holds strictly when `world.bankrupt == True`,
      with no exceptions
- [ ] `graduation_report` for an agent that has "passed" exactly 5 of 6 criteria
      yields `all_passed == False`

### `training_loop.py` — done when:

- [ ] `run_quarters(n_quarters=1)` finishes without raising on
      the minimal configuration (`n_products=1, n_suppliers=1, days=10`)
- [ ] The world inside `training_loop` never receives a `tick()` call
      from code outside `_run_single_quarter`
- [ ] Interrupting a quarter on `world.bankrupt` does not break subsequent quarters
      (a new world is created afresh)

---

## 16. Catalogue of edge cases and failure modes

These cases must be handled explicitly (not merely "must not crash", but must have
meaningful behaviour) before a module is considered finished.

| # | Edge case | Expected behaviour |
|---|---|---|
| E1 | `place_order` with a negative `qty` or `NaN` | `rejected`, `reason="invalid_quantity"` |
| E2 | All suppliers have defaulted (`is_defaulted=True`) | The agent cannot place any order; the world does not crash; a `stockout` is inevitable and expected, not a bug |
| E3 | `n_products=0` in the config | The world is created, `observe_stock_levels()` returns `{}`, `tick()` does not crash |
| E4 | The agent does not implement `step()` (fallback without the core) | `SandboxTrainer._agent_decide` returns `"wait_and_monitor"` and does not crash |
| E5 | `initial_budget=0` | The first day with holding costs leads to `bankrupt=True`; this is a correct outcome, not an anomaly |
| E6 | An order is placed on the last day of the quarter (`arrival_day` falls beyond `days_per_quarter`) | The order remains in `pending_orders` until the end of the quarter; it is not carried into the next one (a new `ProcurementWorld` is created from scratch — see section 8, V1) — **this is a deliberate simplification**; the agent must learn not to place orders that cannot arrive before the end of the planning horizon |
| E7 | Two suppliers with an identical `base_price_multiplier` (a collision under `rng`) | `_cost_efficiency` must not divide by zero; comparison through `min`/`max` handles equality correctly |
| E8 | `sleep_every_n_days` is greater than `days_per_quarter` | The agent never sleeps during the quarter — a valid (though undesirable for learning) scenario, not an error |
| E9 | The agent emits a non-existent `action` (not in `ACTION_TO_ORDER_STRATEGY`) | `_execute_action` returns `{"result": {"status": "no_action"}}` and does not crash |
| E10 | `decision_log` contains entries without the key `"result"` (for example, `wait_and_monitor`) | All fitness functions use `.get("result", {})` and do not raise `KeyError` |

---

## 17. Configuration schema `configs/default_world.yaml`

```yaml
# configs/default_world.yaml
#
# Единая точка настройки параметров песочницы.
# run_sandbox.py должен уметь принимать --config path/to/this.yaml
# в дополнение к текущим CLI-аргументам (CLI переопределяет YAML).

world:
  initial_budget: 100000.0
  n_products: 10
  n_suppliers: 5
  days_per_quarter: 90
  demand_shock_probability: 0.05
  supplier_default_probability: 0.003
  late_delivery_probability_base: 0.05

training:
  n_quarters: 30
  sleep_every_n_days: 7
  stop_on_graduation: true

graduation_thresholds:
  cost_efficiency: 0.60
  stockout_avoidance: 0.85
  budget_discipline: 0.95
  supplier_diversification: 0.40
  decision_consistency: 0.60
  reaction_to_risk_events: 0.50

output:
  results_dir: "results/"
  save_per_quarter_snapshots: true
```
**Implementation requirement:** `GRADUATION_THRESHOLDS` in `procurement_fitness.py`
must be overridable through this YAML, rather than hard-coded —
this will be needed at calibration (section 19).

---

## 18. Glossary

| Term | Definition |
|---|---|
| **Quarter** | One independent run of `ProcurementWorld` for `days_per_quarter` days; the unit of fitness evaluation |
| **Graduation** | The event in which all 6 criteria of `ProcurementFitnessVector` have exceeded their thresholds within a single quarter |
| **Reorder point** | The stock level of a product below which a new purchase is required |
| **Supplier default** | A supplier leaves availability permanently (the analogue of a supplier bankruptcy) |
| **Holding cost** | Daily cost of holding stock, debited from the budget automatically |
| **Decision log** | The list of the agent's actions over a quarter, used by `ProcurementFitnessEvaluator` |
| **Action label** | A symbolic decision of the agent (`"urgent_reorder"` and the like), NOT a full `ActionIntent` with parameters — a temporary simplification (section 12) |
| **Risk day** | A day on which a `supplier_defaulted`, `stockout`, or `demand_shock` event occurred |

---

## 19. Calibration cycle after the first run

As in the Warriner demo, where calibration of `affective_gain` was required
after the first launch, an iteration of parameters will likewise be required
after the first full sandbox run. Plan of action:

### Step 1 — diagnosis

After `run_sandbox.py --quarters 30`, if the agent has **not** graduated:

```
Для каждого из 6 критериев зафиксировать среднее значение
за последние 5 кварталов. Тот критерий, что дальше всего
от порога — узкое место.
```
### Step 2 — table of probable causes by criterion

| Criterion that does not grow | Probable cause | What to check or change |
|---|---|---|
| `cost_efficiency` | The agent does not distinguish cheap from expensive suppliers in memory | Check that `supplier_id` enters `context_events`; strengthen the seed on the event `deal_closed_favorable` |
| `stockout_avoidance` | The agent reacts too late to `below_reorder_point` | Reduce `reorder_point` in the config, or strengthen the arousal signal of the event `stock_critical_low` |
| `budget_discipline` | The agent orders too aggressively | Check that the `budget:critical` token reaches the context when `utilization_ratio > 0.8` |
| `supplier_diversification` | One supplier dominates the decision_log | The `_pick_supplier` heuristic may be too deterministic — more variability is required from the agent itself, not from the heuristic |
| `decision_consistency` | Chaotic decisions for similar situations | May mean that the hippocampus is not consolidating — check that `sleep_cycle()` is in fact called on the boundary of `sleep_every_n_days` |
| `reaction_to_risk_events` | The agent ignores `supplier_defaulted` and `demand_shock` | Strengthen `arousal` in `AFFECTIVE_MAPPING` for risk events |

### Step 3 — parameter sweep (analogue of section 11 of the Warriner specification)

```bash
for SLEEP in 3 7 14; do
  for SHOCK_PROB in 0.02 0.05 0.10; do
    python -m nowa_sandbox.run_sandbox \
      --quarters 30 --sleep-every $SLEEP \
      --output results/sweep_sleep${SLEEP}_shock${SHOCK_PROB}.json
  done
done
```
Record the quarter at which graduation occurs (if it occurs)
for each combination of parameters.

---

## 20. Readiness criteria for Phase 3 (transition to a real MCP)

The sandbox is considered finished, and ready to hand over to a real
MCP connection (parent specification, section 6), when:

- [ ] The agent has reached `graduated = True` in at least 3 of 5 independent runs
      with different `seed` values (not one fortunate accident)
- [ ] The mean number of quarters to graduation is stable (spread no greater than ±50%
      across runs) — otherwise learning is too noisy to be trusted
- [ ] All test cases from section 9 are green
- [ ] A manual review of the `decision_log` of the last successful quarter —
      a person who understands procurement agrees that the agent's decisions
      look reasonable (not a formal metric, but an obligatory check)
- [ ] The final genome values of the successful agent are documented
      (for later use as the "seed genome" of a real employee)

---

## 21. Open questions for the implementing agent

These questions **do not block** the start of implementation (sections 2–7 give enough
to begin), but they must be resolved before the transition to Phase 3:

1. **How should the agent specify order quantity?** The current heuristic
   (`_decide_quantity` = 30 days of demand) is a stub. A decision is required: either
   extend `ActionSelector` to parameterised actions, or introduce
   a separate "quantity" affective signal (higher arousal → a larger order).

2. **Is a multi-candidate initialisation needed?** If one random genome
   regularly fails to reach graduation in a reasonable number of quarters, does it
   make sense (temporarily, only for this phase) to initialise N=5 candidates
   with different genomes and keep the best by `ProcurementFitnessVector`,
   without waiting for a full evolution?

3. **How is the agent's "learned" experience carried into Phase 3?** The agent's hippocampus
   after the sandbox contains episodes about the virtual `supplier_000` and
   `product_003` — these ids do not exist in a real 1C. Is a strategy needed
   for "transfer of patterns, not of concrete ids" (analogous to the way the cortex
   consolidates abstract patterns from concrete hippocampal episodes)?

---

*Specification v1.0 — full version. Sections 1–21.*
*Ready to be handed to the implementing agent for implementation.*

---

## 22. Persistence — saving and restoring learning

### The problem

Thirty or more quarters of 90 days are hours of computation. If the process is interrupted
(a crash, a restart of the environment), the agent's entire progress (hippocampus, consolidated
patterns, genome) must not be lost. This is a separate task from the Warriner demo,
where each run was self-contained and short.

### Contract `SandboxCheckpoint`

```
Обязанность: сохранять состояние ПОСЛЕ каждого квартала, не только в конце.

Что сохраняется:
  - agent.hippocampus (все Experience)
  - agent.cortex (консолидированные паттерны)
  - agent.genome (геном, не меняется, но должен быть зафиксирован)
  - agent.sleep_manager (consolidation_cycles и внутренние счётчики)
  - SandboxTrainingResult целиком (история всех пройденных кварталов)
  - RNG state (для точной воспроизводимости продолжения)

Что НЕ сохраняется:
  - Состояние ProcurementWorld текущего квартала (каждый квартал —
    новый мир по определению, раздел 8 V1)
```
### Implementation requirements

- [ ] Use the existing `AgentStorage` (from the NOWA core) as the basis;
      do not invent a new mechanism for serialising the agent from scratch
- [ ] `run_sandbox.py` must accept `--resume-from <checkpoint_path>`
      and continue from quarter N+1, not from zero
- [ ] A checkpoint must contain the number of the last completed quarter
      and the `graduated` flag — if the agent has already graduated, `--resume` must
      warn explicitly, rather than quietly continue training

### Test case

```python
class TestPersistence:

    def test_checkpoint_roundtrip_preserves_hippocampus_size(
        self, sandbox_agent, tmp_path
    ):
        """После save→load размер гиппокампа не должен измениться."""
        # Засеять несколько эпизодов, сохранить, загрузить в новый агент,
        # сравнить len(hippocampus.experiences)
        ...

    def test_resume_continues_from_correct_quarter(
        self, sandbox_agent, encoder, fitness_evaluator, tmp_path
    ):
        """
        Прогон 2 кварталов, сохранение, resume ещё на 2 кварталa —
        итоговый result.quarters должен содержать 4 записи, не 2.
        """
        ...

    def test_resume_of_already_graduated_agent_warns(
        self, tmp_path
    ):
        """Resume graduated-агента должен явно предупредить пользователя."""
        ...
```

---

## 23. Integration test — full end-to-end cycle

```python
"""tests/test_integration.py — полный прогон песочницы от старта до graduation
или до достижения лимита кварталов, без моков."""

import pytest
from nowa_sandbox.procurement_world import ProcurementWorldConfig
from nowa_sandbox.sandbox_encoder import SandboxEncoder
from nowa_sandbox.procurement_fitness import ProcurementFitnessEvaluator
from nowa_sandbox.sandbox_agent_factory import create_procurement_agent
from nowa_sandbox.training_loop import SandboxTrainer


class TestFullSandboxCycle:

    @pytest.mark.slow
    def test_agent_improves_over_quarters(self):
        """
        Не требует graduation, но проверяет монотонную (в среднем)
        тенденцию улучшения: средний fitness score за последние 5
        кварталов должен быть не хуже, чем за первые 5.

        Это ключевой sanity-check: если агент НЕ улучшается со временем,
        значит consolidation (sleep_cycle) не работает, либо
        affective feedback не доходит до hippocampus.
        """
        import random
        agent = create_procurement_agent("integration_test", rng=random.Random(7))
        encoder = SandboxEncoder()
        fitness_evaluator = ProcurementFitnessEvaluator()
        trainer = SandboxTrainer(agent, encoder, fitness_evaluator, sleep_every_n_days=7)

        config = ProcurementWorldConfig(
            initial_budget=50_000.0, n_products=5, n_suppliers=3,
            days_per_quarter=60,
        )
        result = trainer.run_quarters(
            n_quarters=20, world_config=config, stop_on_graduation=False
        )

        assert len(result.quarters) == 20

        def avg_score(quarters):
            totals = [
                sum(q.fitness.as_dict().values()) / 6.0 for q in quarters
            ]
            return sum(totals) / len(totals)

        first_five = avg_score(result.quarters[:5])
        last_five = avg_score(result.quarters[-5:])

        # Мягкое утверждение: не требуем строгого роста (шумно),
        # но и не допускаем деградации
        assert last_five >= first_five - 0.05, (
            f"Agent fitness degraded: first_five={first_five:.3f}, "
            f"last_five={last_five:.3f}"
        )

    @pytest.mark.slow
    def test_full_pipeline_produces_valid_json_output(self, tmp_path):
        """CLI-эквивалентный прогон: создание агента → тренировка →
        сериализация результата → валидный JSON."""
        import random, json
        from nowa_sandbox.sandbox_observer import SandboxObserver

        agent = create_procurement_agent("json_test", rng=random.Random(3))
        encoder = SandboxEncoder()
        fitness_evaluator = ProcurementFitnessEvaluator()
        trainer = SandboxTrainer(agent, encoder, fitness_evaluator)

        config = ProcurementWorldConfig(
            initial_budget=20_000.0, n_products=3, n_suppliers=2,
            days_per_quarter=30,
        )
        result = trainer.run_quarters(n_quarters=3, world_config=config)

        observer = SandboxObserver()
        for q in result.quarters:
            observer.record(q)

        output_path = tmp_path / "result.json"
        observer.to_json(str(output_path))

        data = json.loads(output_path.read_text())
        assert len(data) == 3
        assert "fitness" in data[0]
        assert "graduation" in data[0]
```

---

## 24. Performance requirements

| Metric | Bound | Justification |
|---|---|---|
| One simulation day (`world.tick()`) | < 5 ms at `n_products=10, n_suppliers=5` | 90 days × 30 quarters = 2700 ticks; it must fit into a reasonable CI time |
| One quarter in full | < 30 s at the standard configuration | Otherwise parameter iteration (section 19) becomes impractical |
| A full run of 30 quarters | < 15 minutes | Acceptable for a local launch by a developer without dedicated infrastructure |
| Memory for one agent after 30 quarters | < 200 MB | The hippocampus has a `max_experiences` cap — it must not grow without bound |

If an implementation exceeds these bounds, profile first
`sleep_cycle()` (usually the heaviest operation) and `_pick_priority_product`
(potentially O(n_products) on every day, which is acceptable at a reasonable
n_products, but worth checking at scale).

---

## 25. Specification versioning

| Version | Changes |
|---|---|
| 1.0 | Initial architecture: world/encoder/fitness/training_loop/observer, full test cases, constraints, edge cases, interface contracts, persistence, integration tests, performance requirements |

**Relation to the parent document:** `NOWA_Virtual_Employees_Architecture_Spec.md`,
section 5. After the criteria of section 20 of this document are met — transition
to a detailed account of Phase 1 (Body Layer) or Phase 3 (a real MCP connection)
of the parent specification.

---

*End of the specification. Sections 1–25. Ready to be handed to the implementing agent.*

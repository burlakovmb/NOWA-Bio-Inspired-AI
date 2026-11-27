## Аннотация

English version: [NOWA_Procurement_Sandbox_Spec.en.md](NOWA_Procurement_Sandbox_Spec.en.md)

Настоящая спецификация задаёт контур `nowa_sandbox` версии 1.0: контролируемый рынок закупок, в котором один суверенный экземпляр NOWA обучается роли закупщика до любого обращения к реальным данным протокола MCP. Мир `ProcurementWorld` выступает пассивной физикой. Конфигурация по умолчанию фиксирует начальный бюджет 100 000, десять товаров, пять поставщиков и квартал в девяносто дней; вероятность шока спроса равна 0,05, вероятность дефолта поставщика — 0,003 на поставщика в сутки. Сутки продвигает только `tick()`, вызываемый тренировочным циклом. Агент получает категориальные токены `context_events` и не читает внутренние поля мира. Консолидация опыта допускается исключительно в фазе сна, по умолчанию каждые семь суток. Шлюз одобрения в этом контуре отключён намеренно: виртуальный `place_order` исполняется сразу, поскольку денежные величины здесь являются тренировочным сигналом. Модуль мира не импортирует клиенты MCP и тем самым не пересекается с протокольным телом.

Пригодность описывается шестимерным вектором: эффективность затрат, избежание дефицита, бюджетная дисциплина, диверсификация поставщиков, согласованность решений и реакция на риск. **Актуальные** пороги в коде и в `configs/default_world.yaml` — `procurement_fitness.GRADUATION_THRESHOLDS` (в частности `decision_consistency` **0.79**, не 0.60); определения: [issue-76-vc-graduation-metrics.ru.md](../../../Docs/specs/issue-76-vc-graduation-metrics.ru.md). В двухстадийной программе v1.1 в каждом квартале гейтят только критерии текущей стадии. В этой версии агент выбирает дискретную стратегию поставщика, а объём заказа задаётся эвристикой покрытия около тридцати дней среднего спроса. Каждый квартал создаёт новый мир; зерно воспроизводимости равно индексу квартала, состояние агента между кварталами сохраняется.

Документ фиксирует контракты методов наблюдения и записи, каталог краевых случаев, требования к контрольной точке после каждого квартала и границы производительности: один `tick()` короче 5 мс при штатном размере мира, квартал короче 30 с, прогон в тридцать кварталов короче 15 минут, память одного агента после такого прогона меньше 200 МБ. Переход к реальному подключению MCP спецификация ставит в зависимость от выпуска не менее чем в трёх из пяти независимых прогонов при разбросе числа кварталов до выпуска не более ±50 %. Пример текста командной строки в разделе запуска иллюстрирует формат отчёта и не является зарегистрированным итогом эксперимента.

---

# NOWA Procurement Sandbox — Техническая спецификация

**Версия:** 1.0
**Статус:** готово к реализации
**Родительский документ:** NOWA_Virtual_Employees_Architecture_Spec.md (раздел 5)
**Цель:** Обучить одного NOWA-агента ("Закупщик") принимать решения о
закупках в симулированном мире, до какого-либо контакта с реальными
MCP-данными или реальными деньгами.

---

## 0. Принципы (наследуются)

1. **Агент суверенен.** Один агент — один независимый экземпляр NOWA.
   Песочница не управляет агентом, она только: (а) выдаёт наблюдения через
   публичный интерфейс, (б) принимает действия агента, (в) обновляет своё
   внутреннее состояние независимо от воли агента — как физика.
2. **Обучение только во сне.** `sleep_manager.sleep_cycle()` — единственный
   механизм консолидации памяти в паттерны. Днём (тик бодрствования) агент
   принимает решения на основе уже консолидированного опыта, не переобучаясь.
3. **Approval gate в песочнице отключён намеренно.** Здесь нет реальных
   денег — `world.place_order()` исполняется немедленно. Это единственное
   место во всей системе, где действие агента не проходит approval —
   потому что "деньги" здесь виртуальны и являются частью тренировочного
   сигнала, а не риском.
4. **Не смешивать симуляцию и реальность.** `ProcurementWorld` никогда не
   вызывает настоящие MCP-тулы. Любой код, который случайно подключит
   песочницу к реальному 1С — архитектурная ошибка (см. раздел 8, C1).

---

## 1. Структура проекта
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

## 2. Модуль `procurement_world.py`

### 2.1 Полная реализация
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

## 3. Модуль `sandbox_encoder.py`

### 3.1 World state → context_events (аналог WordStimulusEncoder)
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

## 4. Модуль `procurement_fitness.py`

### 4.1 Полная реализация
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

## 5. Модуль `sandbox_agent_factory.py`

### 5.1 Создание одного агента для песочницы
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

## 6. Модуль `training_loop.py`

### 6.1 Полная реализация
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

## 7. Модуль `sandbox_observer.py`

### 7.1 Пассивное наблюдение (для диагностики, не для управления)
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

## 8. Ограничения системы

### 8.1 Архитектурные ограничения (нарушение = баг)

| # | Ограничение | Обоснование |
|---|---|---|
| **C1** | `ProcurementWorld` никогда не импортирует и не вызывает MCP-клиенты | Изоляция симуляции от реальности — критично для безопасности |
| **C2** | `world.tick()` вызывается ТОЛЬКО из `training_loop`, не из кода агента | Мир — физика, не подчиняется воле агента |
| **C3** | `agent.step()` не имеет доступа к внутренним полям `ProcurementWorld` (только к результатам `observe_*` методов) | Агент видит мир через "органы чувств", не через интроспекцию |
| **C4** | `sleep_manager.sleep_cycle()` — единственный способ модификации весов/паттернов агента | Не переобучаться в течение дня |
| **C5** | Один `SandboxTrainer` работает с одним агентом за раз | Нет скрытой популяционной динамики в этой фазе |

### 8.2 Валидационные ограничения

| # | Ограничение | Обоснование |
|---|---|---|
| **V1** | Каждый квартал использует новый `ProcurementWorld` с фиксированным seed = quarter_index | Воспроизводимость, но разнообразие сценариев |
| **V2** | `graduation_report` требует **всех** 6 критериев ≥ порога, не среднего | Нельзя компенсировать провал по бюджетной дисциплине успехом в другом |
| **V3** | Минимум 20 кварталов до первой попытки graduation-проверки | Достаточно данных для стабильной оценки |
| **V4** | `_decide_quantity` использует фиксированную эвристику (30 дней спроса), не решение агента | В этой версии песочницы агент выбирает *стратегию поставщика*, не точный объём — упрощение для первой итерации |

### 8.3 Статистические ограничения

| # | Параметр | Минимум | Рекомендуемое |
|---|---|---|---|
| **S1** | `n_quarters` | 20 | 30–50 |
| **S2** | `days_per_quarter` | 60 | 90 |
| **S3** | `n_products` | 5 | 10–20 |
| **S4** | `n_suppliers` | 3 | 5–8 |
| **S5** | `sleep_every_n_days` | 5 | 7 |

---

## 9. Тест-кейсы

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

### Пример запуска
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

Ожидаемый вывод:
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

Песочница намеренно не требует ML-зависимостей (нет SBERT, нет CLIP) —
она работает на символических токенах и детерминированной физике.

---

## 12. Известные упрощения текущей версии (для следующей итерации)

| Упрощение | Почему сейчас так | Что улучшить позже |
|---|---|---|
| Агент выбирает *стратегию* (`highest_reliability` и т.п.), не точные параметры заказа | `ActionSelector` в NOWA работает с фиксированным набором дискретных действий, полноценный `ActionIntent` с параметрами — следующий шаг | Расширить `Agent` до генерации структурированного `ActionIntent(supplier_id=..., qty=...)` |
| `_decide_quantity` — фиксированная эвристика (30 дней спроса) | Упрощение для первой обучаемой версии | Агент должен сам решать объём на основе `demand_volatility` и `lead_time` |
| Один агент, не популяция кандидатов | Соответствует финальной архитектуре ("один сотрудник") | Можно временно ввести отбор из N кандидатов по `ProcurementFitnessVector` для ускорения поиска хорошего генома |
| Нет явного `RealizationExperience` для текста писем поставщикам | Песочница не включает NLG-слой | Добавить при переходе на Stage 2 (там уже нужны реальные письма) |

---

## 13. Порядок реализации

### День 1–2: физика мира
1. `procurement_world.py` — полная реализация
2. `tests/test_procurement_world.py` — все тесты зелёные
3. Ручная проверка: 90 дней без единого заказа → должен появиться stockout

### День 3: encoder и fitness
4. `sandbox_encoder.py`
5. `procurement_fitness.py`
6. `tests/test_sandbox_encoder.py`, `tests/test_procurement_fitness.py`

### День 4–5: агент и тренировочный цикл
7. `sandbox_agent_factory.py`
8. `training_loop.py`
9. `tests/test_training_loop.py`, `tests/test_agent_independence.py`

### День 6: CLI и первый прогон
10. `run_sandbox.py`
11. `sandbox_observer.py`
12. Первый прогон на 30 кварталов, зафиксировать: graduated ли агент,
    на каком квартале, какие критерии подтягиваются медленнее всего

### День 7: анализ и итерация
13. Если не graduated за 30 кварталов — анализ per-criterion (какой из
    шести отстаёт) → корректировка genome defaults или affective seed
14. Подготовка к переходу на Фазу 3 родительской спецификации
    (реальное MCP-подключение)

---

*Спецификация v1.0. Готова к передаче агенту-разработчику.*
*Следующий документ: детализация Фазы 1 (универсальный MCP Body Layer)
или итерация после первого прогона песочницы — в зависимости от того,
что будет готово раньше.*

---

## 14. Контракты интерфейсов (сигнатуры без реализации)

Ниже — минимальный контракт каждого публичного метода. Реализация в разделах
2–7 — референсная, агент-разработчик может отклоняться от неё в деталях,
но обязан сохранить эти сигнатуры и поведенческие гарантии.

### `ProcurementWorld`

| Метод | Возвращает | Гарантия |
|---|---|---|
| `observe_stock_levels()` | `Dict[str, dict]` | Не мутирует состояние мира |
| `observe_supplier_quote(supplier_id, product_id, qty)` | `dict` | Идемпотентен относительно чтения; цена содержит случайный шум, но не мутирует `budget` |
| `observe_budget_status()` | `dict` | Не мутирует состояние |
| `observe_supplier_directory()` | `Dict[str, dict]` | Не мутирует состояние |
| `observe_pending_orders()` | `List[dict]` | Не мутирует состояние |
| `place_order(supplier_id, product_id, qty)` | `dict` со `status` | Единственный write-метод; либо списывает `budget`, либо возвращает `rejected` без побочных эффектов |
| `tick()` | `dict` | Единственный метод, продвигающий `day`; вызывается только из `training_loop`, никогда из кода агента |
| `summary()` | `dict` | Не мутирует состояние |

**Инвариант:** после любого количества вызовов `observe_*` без `place_order`
и `tick`, состояние мира побитово идентично исходному.

### `SandboxEncoder`

| Метод | Контракт |
|---|---|
| `encode_daily_context(world, tick_result) -> List[str]` | Всегда непустой список; никогда не содержит числовых значений валентности напрямую (только токены `valence:*` категориального типа) |
| `encode_seed_episode(event_name) -> dict` | Для неизвестного `event_name` возвращает нейтральный дефолт, не бросает исключение |

**Инвариант:** вызов с одинаковыми `world`/`tick_result` детерминирован
(при фиксированном `AFFECTIVE_MAPPING`).

### `ProcurementFitnessEvaluator`

| Метод | Контракт |
|---|---|
| `evaluate(world, decision_log) -> ProcurementFitnessVector` | Каждое поле вектора строго в `[0.0, 1.0]`; пустой `decision_log` не бросает исключение, даёт нейтральные (0.5) оценки для критериев, зависящих от заказов |
| `graduation_report(vector) -> dict` | `all_passed = True` **только если** все 6 критериев прошли порог; частичное прохождение никогда не даёт `all_passed = True` |

### `SandboxTrainer`

| Метод | Контракт |
|---|---|
| `run_quarters(n_quarters, world_config, ...) -> SandboxTrainingResult` | Каждый квартал использует **новый** `ProcurementWorld` (не переносит state между кварталами, кроме состояния агента) |
| Внутренний вызов `agent.sleep_manager.sleep_cycle()` | Происходит **только** на границе `sleep_every_n_days`, не чаще и не по требованию агента |

**Инвариант:** агент, переданный в `SandboxTrainer`, — единственный источник
решений; `_pick_priority_product` / `_pick_supplier` / `_decide_quantity` —
это **временный эвристический слой** (раздел 12), который в финальной версии
должен быть заменён полями `ActionIntent`, генерируемыми агентом напрямую.

---

## 15. Критерии приёмки — определение готовности по модулям

### `procurement_world.py` — готово, когда:

- [ ] Мир без единого действия агента за 90 дней самостоятельно генерирует
      минимум 1 событие `stockout` (спрос превышает начальный сток)
- [ ] Мир с постоянными избыточными заказами (много закупок каждый день)
      достигает `bankrupt = True` до истечения 90 дней
- [ ] `place_order` с корректными параметрами всегда либо `accepted`,
      либо `rejected` с непустым `reason`
- [ ] Два мира с одинаковым `seed` дают побитово идентичную историю
      при одинаковой последовательности вызовов
- [ ] Мир с `n_suppliers=0` не падает (обрабатывает как краевой случай,
      см. раздел 16)

### `sandbox_encoder.py` — готово, когда:

- [ ] Ни один токен из `encode_daily_context` не содержит сырых чисел
      (только категориальные `valence:*`, `arousal:*`, `status:*`)
- [ ] `AFFECTIVE_MAPPING["bankruptcy"]` — самое негативное событие
      по valence среди всех записей карты
- [ ] Пустой `world` (0 товаров) не приводит к исключению

### `procurement_fitness.py` — готово, когда:

- [ ] Все 6 критериев для `evaluate([], [])` (нулевая история) возвращают
      значения в `[0, 1]` без исключений
- [ ] `budget_discipline == 0.0` строго при `world.bankrupt == True`,
      без исключений
- [ ] `graduation_report` для агента, "прошедшего" ровно 5 из 6 критериев,
      даёт `all_passed == False`

### `training_loop.py` — готово, когда:

- [ ] `run_quarters(n_quarters=1)` завершается без исключений на
      минимальной конфигурации (`n_products=1, n_suppliers=1, days=10`)
- [ ] Мир внутри `training_loop` никогда не получает вызов `tick()`
      от кода вне `_run_single_quarter`
- [ ] Прерывание квартала на `world.bankrupt` не ломает последующие кварталы
      (новый мир создаётся заново)

---

## 16. Каталог краевых случаев и режимов отказа

Эти случаи должны быть явно обработаны (не просто "не упасть", а иметь
осмысленное поведение), прежде чем считать модуль завершённым.

| # | Краевой случай | Ожидаемое поведение |
|---|---|---|
| E1 | `place_order` с `qty` отрицательным или `NaN` | `rejected`, `reason="invalid_quantity"` |
| E2 | Все поставщики дефолтнули (`is_defaulted=True`) | Агент не может разместить ни одного заказа; мир не падает; `stockout` неизбежен и это ожидаемо, не баг |
| E3 | `n_products=0` в конфиге | Мир создаётся, `observe_stock_levels()` возвращает `{}`, `tick()` не падает |
| E4 | Агент не реализует `step()` (fallback без core) | `SandboxTrainer._agent_decide` возвращает `"wait_and_monitor"`, не падает |
| E5 | `initial_budget=0` | Первый же день с holding costs уводит в `bankrupt=True`; это корректный, а не аномальный исход |
| E6 | Заказ размещён в последний день квартала (`arrival_day` выходит за `days_per_quarter`) | Заказ остаётся в `pending_orders` до конца квартала; не переносится в следующий (новый `ProcurementWorld` создаётся с нуля — см. раздел 8, V1) — **это осознанное упрощение**, агент должен научиться не размещать заказы, которые не успеют прийти до конца горизонта планирования |
| E7 | Два поставщика с идентичной `base_price_multiplier` (совпадение по `rng`) | `_cost_efficiency` не должен делить на ноль; сравнение через `min`/`max` корректно обрабатывает равенство |
| E8 | `sleep_every_n_days` больше, чем `days_per_quarter` | Агент ни разу не засыпает за квартал — валидный (хотя и нежелательный для обучения) сценарий, не ошибка |
| E9 | Агент вызывает несуществующий `action` (не из `ACTION_TO_ORDER_STRATEGY`) | `_execute_action` возвращает `{"result": {"status": "no_action"}}`, не падает |
| E10 | `decision_log` содержит записи без ключа `"result"` (например, `wait_and_monitor`) | Все fitness-функции используют `.get("result", {})`, не падают на `KeyError` |

---

## 17. Схема конфигурации `configs/default_world.yaml`
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

**Требование к реализации:** `GRADUATION_THRESHOLDS` в `procurement_fitness.py`
должен быть переопределяем через этот YAML, а не жёстко захардкожен —
это понадобится при калибровке (раздел 19).

---

## 18. Глоссарий

| Термин | Определение |
|---|---|
| **Квартал (quarter)** | Один независимый запуск `ProcurementWorld` на `days_per_quarter` дней; единица оценки fitness |
| **Graduation** | Событие: все 6 критериев `ProcurementFitnessVector` превысили пороги в рамках одного квартала |
| **Reorder point** | Уровень стока товара, ниже которого требуется новая закупка |
| **Supplier default** | Поставщик безвозвратно выходит из доступности (аналог банкротства поставщика) |
| **Holding cost** | Ежедневные издержки на хранение стока, списываются с бюджета автоматически |
| **Decision log** | Список действий агента за квартал, используется `ProcurementFitnessEvaluator` |
| **Action label** | Символическое решение агента (`"urgent_reorder"` и т.п.), НЕ полноценный `ActionIntent` с параметрами — временное упрощение (раздел 12) |
| **Risk day** | День, в который произошло событие `supplier_defaulted`, `stockout` или `demand_shock` |

---

## 19. Калибровочный цикл после первого прогона

Аналогично тому, как в Warriner-демо после первого запуска потребовалась
калибровка `affective_gain`, здесь тоже потребуется итерация параметров
после первого полного прогона песочницы. План действий:

### Шаг 1 — диагностика

После `run_sandbox.py --quarters 30`, если агент **не** graduated:
```
Для каждого из 6 критериев зафиксировать среднее значение
за последние 5 кварталов. Тот критерий, что дальше всего
от порога — узкое место.
```

### Шаг 2 — таблица вероятных причин по критерию

| Критерий не растёт | Вероятная причина | Что проверить/менять |
|---|---|---|
| `cost_efficiency` | Агент не различает дешёвых/дорогих поставщиков в памяти | Проверить, что `supplier_id` попадает в `context_events`; усилить seed по событию `deal_closed_favorable` |
| `stockout_avoidance` | Агент реагирует слишком поздно на `below_reorder_point` | Уменьшить `reorder_point` в конфиге, либо усилить arousal-сигнал события `stock_critical_low` |
| `budget_discipline` | Агент заказывает слишком агрессивно | Проверить, что `budget:critical` токен доходит до контекста при `utilization_ratio > 0.8` |
| `supplier_diversification` | Один поставщик доминирует в decision_log | Возможно, `_pick_supplier` эвристика слишком детерминирована — потребуется больше вариативности от самого агента, не от эвристики |
| `decision_consistency` | Хаотичные решения для похожих ситуаций | Может означать, что гиппокамп не консолидируется — проверить, действительно ли `sleep_cycle()` вызывается на границе `sleep_every_n_days` |
| `reaction_to_risk_events` | Агент игнорирует `supplier_defaulted`/`demand_shock` | Усилить `arousal` в `AFFECTIVE_MAPPING` для риск-событий |

### Шаг 3 — sweep параметров (аналог раздела 11 Warriner-спеки)
```bash
for SLEEP in 3 7 14; do
  for SHOCK_PROB in 0.02 0.05 0.10; do
    python -m nowa_sandbox.run_sandbox \
      --quarters 30 --sleep-every $SLEEP \
      --output results/sweep_sleep${SLEEP}_shock${SHOCK_PROB}.json
  done
done
```

Зафиксировать: на каком кварталe наступает graduation (если наступает)
для каждой комбинации параметров.

---

## 20. Критерии готовности к Фазе 3 (переход на реальный MCP)

Песочница считается завершённой и готовой передать эстафету реальному
MCP-подключению (родительская спецификация, раздел 6), когда:

- [ ] Агент достиг `graduated = True` минимум в 3 из 5 независимых прогонов
      с разными `seed` (не одна счастливая случайность)
- [ ] Среднее число кварталов до graduation стабильно (разброс не более ±50%
      между прогонами) — иначе обучение слишком шумное для доверия
- [ ] Все тест-кейсы из раздела 9 зелёные
- [ ] Ручной review `decision_log` последнего успешного квартала —
      человек, разбирающийся в закупках, соглашается, что решения агента
      выглядят разумными (не формальная метрика, но обязательная проверка)
- [ ] Задокументированы финальные значения генома успешного агента
      (для последующего использования как "seed genome" реального сотрудника)

---

## 21. Открытые вопросы для агента-разработчика

Эти вопросы **не блокируют** начало реализации (разделы 2–7 дают достаточно
для старта), но должны быть решены до перехода к Фазе 3:

1. **Как агент должен указывать объём заказа?** Текущая эвристика
   (`_decide_quantity` = 30 дней спроса) — заглушка. Нужно решить: либо
   расширять `ActionSelector` до параметризованных действий, либо вводить
   отдельный "объёмный" аффективный сигнал (выше arousal → больше заказ).

2. **Нужна ли multi-candidate инициализация?** Если один случайный геном
   регулярно не достигает graduation за разумное число кварталов — имеет ли
   смысл (временно, только для этой фазы) инициализировать N=5 кандидатов
   с разными геномами и оставить лучшего по `ProcurementFitnessVector`,
   не дожидаясь полноценной эволюции?

3. **Как переносить "выученный" опыт агента в Фазу 3?** Гиппокамп агента
   после песочницы содержит эпизоды про виртуальных `supplier_000` и
   `product_003` — эти id не существуют в реальном 1С. Нужна ли стратегия
   "переноса паттернов, не конкретных id" (аналогично тому, как cortex
   консолидирует абстрактные паттерны из конкретных эпизодов hippocampus)?

---

*Спецификация v1.0 — полная версия. Разделы 1–21.*
*Готова к передаче агенту-разработчику для реализации.*

---

## 22. Персистентность — сохранение и восстановление обучения

### Проблема

30+ кварталов по 90 дней — это часы вычислений. Если процесс прервётся
(краш, перезапуск среды), весь прогресс агента (гиппокамп, консолидированные
паттерны, геном) не должен теряться. Это отдельная задача от Warriner-демо,
где каждый прогон был самодостаточным и коротким.

### Контракт `SandboxCheckpoint`
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

### Требования к реализации

- [ ] Использовать существующий `AgentStorage` (из ядра NOWA) как основу,
      не изобретать новый механизм сериализации агента с нуля
- [ ] `run_sandbox.py` должен принимать `--resume-from <checkpoint_path>`
      и продолжать с квартала N+1, а не с нуля
- [ ] Чекпоинт должен содержать номер последнего завершённого квартала
      и флаг `graduated` — если агент уже graduated, `--resume` должен
      явно предупреждать, а не тихо продолжать тренировку

### Тест-кейс
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

## 23. Интеграционный тест — полный цикл end-to-end
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

## 24. Требования к производительности

| Метрика | Ограничение | Обоснование |
|---|---|---|
| Один день симуляции (`world.tick()`) | < 5 мс при `n_products=10, n_suppliers=5` | 90 дней × 30 кварталов = 2700 тиков; должно укладываться в разумное время CI |
| Один квартал целиком | < 30 сек при стандартной конфигурации | Иначе итерация параметров (раздел 19) станет непрактичной |
| Полный прогон 30 кварталов | < 15 минут | Приемлемо для локального запуска разработчиком без выделенной инфраструктуры |
| Память на одного агента после 30 кварталов | < 200 MB | Гиппокамп имеет `max_experiences` cap — не должен расти неограниченно |

Если реализация превышает эти пороги — профилировать в первую очередь
`sleep_cycle()` (обычно самая тяжёлая операция) и `_pick_priority_product`
(потенциально O(n_products) на каждый день, что нормально при разумном
n_products, но стоит проверить на масштабе).

---

## 25. Версионирование спецификации

| Версия | Изменения |
|---|---|
| 1.0 | Исходная архитектура: world/encoder/fitness/training_loop/observer, полные тест-кейсы, ограничения, краевые случаи, контракты интерфейсов, персистентность, интеграционные тесты, требования к производительности |

**Связь с родительским документом:** `NOWA_Virtual_Employees_Architecture_Spec.md`,
раздел 5. После выполнения критериев раздела 20 этого документа — переход
к детализации Фазы 1 (Body Layer) или Фазы 3 (реальное MCP-подключение)
родительской спецификации.

---

*Конец спецификации. Разделы 1–25. Готова к передаче агенту-разработчику.*

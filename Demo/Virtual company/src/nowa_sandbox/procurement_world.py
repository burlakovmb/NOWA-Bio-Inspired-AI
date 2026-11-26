"""Simulated procurement market for NOWA sandbox training.

The world is passive physics: it exposes observations, accepts orders and
advances its own state on ``tick()``. It never imports or calls MCP clients
(architectural constraint C1) — everything here is virtual.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ._common import clamp, is_finite_number, safe_float, safe_int


OfferKey = Tuple[str, str]


def offer_key(product_id: str, supplier_id: str) -> OfferKey:
    return (str(product_id), str(supplier_id))


def product_replenishment_point(
    reorder_point: float,
    base_demand_per_day: float,
    demand_volatility: float,
    lead_time_days: int,
) -> float:
    """Inventory position at which a replenishment must be launched.

    ``reorder_point`` is a user-authored floor. If it sits below lead-time
    demand, using it as the only trigger guarantees a stockout: the motor
    cannot order until on-hand is already too late to cover the pipeline.
    """
    demand = max(0.0, safe_float(base_demand_per_day, 0.0))
    vol = max(0.0, safe_float(demand_volatility, 0.0))
    lead = max(0, int(lead_time_days))
    # +1 day of demand covers the one-SKU-per-day motor cadence.
    cover = demand * lead * (1.0 + vol) + demand
    return max(safe_float(reorder_point, 0.0), cover)


@dataclass
class SupplierOffer:
    """Per-(product, supplier) commercial terms for curriculum worlds."""

    product_id: str
    supplier_id: str
    unit_price: float = 1.0
    lead_time_days: int = 5
    reliability: float = 0.9
    price_volatility: float = 0.05


@dataclass
class VirtualSupplier:
    supplier_id: str
    reliability: float              # [0,1] probability of delivering on time
    base_price_multiplier: float    # relative to the "fair" market price
    price_volatility: float         # std of price noise between quotes
    lead_time_days: int
    reputation: float = 0.5         # grows on successful orders, falls on failures
    total_orders: int = 0
    successful_orders: int = 0
    is_defaulted: bool = False      # supplier vanished (bankruptcy / contract break)

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
    late_delivery_probability_base: float = 0.05  # modulated by (1 - reliability)
    seed: Optional[int] = None
    persistent_suppliers: bool = False
    """Whether supplier identity means anything across quarters (spec 26.6).

    False (Stage 1a): ``supplier_id`` is a stable string, but the
    ``VirtualSupplier`` behind it is regenerated with fresh random attributes
    for every world, so what the agent learned about "supplier_002" last
    quarter describes a different counterparty this quarter.

    True (Stage 1b): attributes are carried over from the previous quarter via
    :meth:`ProcurementWorld.carry_supplier_state`, so relationships are worth
    building. Only ``is_defaulted`` resets, which lets a supplier that failed
    once earn trust back instead of being dead for the rest of the run.
    """

    # Q3b difficulty bounding (spec v1.3) — eliminate structurally impossible
    # quarters where stockout_avoidance cannot succeed regardless of strategy.
    max_lead_time_days: int = 10
    """Upper bound for supplier lead time (was hardcoded 21)."""

    max_demand_per_day: float = 30.0
    """Upper bound for base_demand_per_day (was 50)."""

    min_reorder_days: float = 7.0
    max_reorder_days: float = 15.0
    """Reorder point expressed in days of demand (was 5..12)."""

    min_initial_stock_days: float = 15.0
    max_initial_stock_days: float = 25.0
    """Initial stock expressed in days of demand (was 10..30)."""

    max_demand_volatility: float = 0.30
    """Upper bound for product demand_volatility (was 0.40)."""

    min_supplier_reliability: float = 0.80
    """Floor for supplier reliability (was 0.70)."""

    max_price_volatility: float = 0.10
    """Upper bound for supplier price_volatility (was 0.15)."""

    def __post_init__(self) -> None:
        self.persistent_suppliers = bool(self.persistent_suppliers)
        self.initial_budget = max(0.0, safe_float(self.initial_budget, 0.0))
        self.n_products = safe_int(self.n_products, 0, minimum=0)
        self.n_suppliers = safe_int(self.n_suppliers, 0, minimum=0)
        self.days_per_quarter = safe_int(self.days_per_quarter, 0, minimum=0)
        self.demand_shock_probability = clamp(
            safe_float(self.demand_shock_probability, 0.0), 0.0, 1.0
        )
        self.supplier_default_probability = clamp(
            safe_float(self.supplier_default_probability, 0.0), 0.0, 1.0
        )
        self.late_delivery_probability_base = clamp(
            safe_float(self.late_delivery_probability_base, 0.0), 0.0, 1.0
        )
        self.max_lead_time_days = max(3, safe_int(self.max_lead_time_days, 10, minimum=3))
        self.max_demand_per_day = max(5.0, safe_float(self.max_demand_per_day, 30.0))
        self.min_reorder_days = max(0.0, safe_float(self.min_reorder_days, 7.0))
        self.max_reorder_days = max(
            self.min_reorder_days, safe_float(self.max_reorder_days, 15.0)
        )
        self.min_initial_stock_days = max(
            0.0, safe_float(self.min_initial_stock_days, 15.0)
        )
        self.max_initial_stock_days = max(
            self.min_initial_stock_days,
            safe_float(self.max_initial_stock_days, 25.0),
        )
        self.max_demand_volatility = clamp(
            safe_float(self.max_demand_volatility, 0.30), 0.0, 1.0
        )
        self.min_supplier_reliability = clamp(
            safe_float(self.min_supplier_reliability, 0.80), 0.0, 0.99
        )
        self.max_price_volatility = clamp(
            safe_float(self.max_price_volatility, 0.10), 0.0, 1.0
        )


def quarter_world_seed(base_seed: Optional[int], quarter_index: int) -> int:
    """Seed of one RNG quarter.

    ``base_seed is None`` keeps the historical quarter-index seed.
    A set base seed uses ``base_seed * 1000 + quarter`` (1-based), so
    seed 2 quarter 30 is not the same world as seed 1 quarter 31.
    """
    quarter = int(quarter_index)
    if base_seed is None:
        return quarter
    return int(base_seed) * 1000 + quarter


class ProcurementWorld:
    """Simulated procurement market.

    Analogous to SwarmEnvironment: a passive environment in which a sovereign
    agent acts through a limited set of observations and actions, while the
    environment runs its own physics (``tick``) independent of agent decisions.
    """

    def __init__(
        self,
        config: ProcurementWorldConfig,
        *,
        _skip_rng_init: bool = False,
    ):
        self.config = config
        self.rng = random.Random(config.seed)
        self.day = 0
        self.budget = float(config.initial_budget)
        self.initial_budget = float(config.initial_budget)
        self.offers: Dict[OfferKey, SupplierOffer] = {}
        if _skip_rng_init:
            self.products = {}
            self.suppliers = {}
        else:
            self.products: Dict[str, VirtualProduct] = self._init_products()
            self.suppliers: Dict[str, VirtualSupplier] = self._init_suppliers()
        self.pending_orders: List[PendingOrder] = []
        self.delivered_orders: List[PendingOrder] = []
        self.day_events: List[dict] = []       # events of the latest tick()
        self.history: List[dict] = []          # accumulated per-day history
        self.bankrupt = False
        self._order_counter = 0
        # Quote noise is derived from this salt instead of self.rng so that
        # observe_* calls stay pure (see the invariant in spec section 14).
        self._quote_salt = f"quote|{config.seed}"

    @classmethod
    def from_quarter_spec(
        cls,
        spec: Mapping[str, Any],
        *,
        days_per_quarter: int = 90,
        seed: Optional[int] = None,
        persistent_suppliers: bool = False,
        demand_shock_probability: Optional[float] = None,
        supplier_default_probability: Optional[float] = None,
    ) -> "ProcurementWorld":
        """Build a world solely from an authored quarter curriculum snapshot."""
        budget = safe_float(spec.get("budget"), 100_000.0)
        if "initial_budget" in spec and spec["initial_budget"] is not None:
            budget = safe_float(spec["initial_budget"], budget)
        cfg = ProcurementWorldConfig(
            initial_budget=budget,
            n_products=0,
            n_suppliers=0,
            days_per_quarter=max(1, int(days_per_quarter)),
            seed=seed,
            persistent_suppliers=bool(persistent_suppliers),
            demand_shock_probability=(
                float(demand_shock_probability)
                if demand_shock_probability is not None
                else 0.05
            ),
            supplier_default_probability=(
                float(supplier_default_probability)
                if supplier_default_probability is not None
                else 0.003
            ),
        )
        world = cls(cfg, _skip_rng_init=True)
        world.budget = budget
        world.initial_budget = budget

        for row in spec.get("products") or []:
            if not isinstance(row, Mapping):
                continue
            pid = str(row.get("product_id") or "").strip()
            if not pid:
                continue
            world.products[pid] = VirtualProduct(
                product_id=pid,
                base_demand_per_day=safe_float(row.get("base_demand_per_day"), 10.0),
                demand_volatility=clamp(
                    safe_float(row.get("demand_volatility"), 0.15), 0.0, 1.0
                ),
                holding_cost_per_unit=safe_float(row.get("holding_cost_per_unit"), 1.0),
                stockout_penalty_per_unit=safe_float(
                    row.get("stockout_penalty_per_unit"), 10.0
                ),
                current_stock=safe_float(row.get("current_stock"), 100.0),
                reorder_point=safe_float(row.get("reorder_point"), 50.0),
                cumulative_stockout_units=safe_float(
                    row.get("cumulative_stockout_units"), 0.0
                ),
                cumulative_holding_cost=safe_float(
                    row.get("cumulative_holding_cost"), 0.0
                ),
            )

        for row in spec.get("suppliers") or []:
            if not isinstance(row, Mapping):
                continue
            sid = str(row.get("supplier_id") or "").strip()
            if not sid:
                continue
            world.suppliers[sid] = VirtualSupplier(
                supplier_id=sid,
                reliability=clamp(safe_float(row.get("reliability"), 0.9), 0.0, 1.0),
                base_price_multiplier=safe_float(
                    row.get("base_price_multiplier"), 1.0
                ),
                price_volatility=clamp(
                    safe_float(row.get("price_volatility"), 0.05), 0.0, 1.0
                ),
                lead_time_days=max(1, safe_int(row.get("lead_time_days"), 5, minimum=1)),
                reputation=clamp(safe_float(row.get("reputation"), 0.5), 0.0, 1.0),
                total_orders=max(0, safe_int(row.get("total_orders"), 0, minimum=0)),
                successful_orders=max(
                    0, safe_int(row.get("successful_orders"), 0, minimum=0)
                ),
                is_defaulted=bool(row.get("is_defaulted", False)),
            )

        for row in spec.get("offers") or []:
            if not isinstance(row, Mapping):
                continue
            pid = str(row.get("product_id") or "").strip()
            sid = str(row.get("supplier_id") or "").strip()
            if not pid or not sid:
                continue
            if pid not in world.products or sid not in world.suppliers:
                continue
            offer = SupplierOffer(
                product_id=pid,
                supplier_id=sid,
                unit_price=max(0.01, safe_float(row.get("unit_price"), 1.0)),
                lead_time_days=max(1, safe_int(row.get("lead_time_days"), 5, minimum=1)),
                reliability=clamp(safe_float(row.get("reliability"), 0.9), 0.0, 1.0),
                price_volatility=clamp(
                    safe_float(row.get("price_volatility"), 0.05), 0.0, 1.0
                ),
            )
            world.offers[offer_key(pid, sid)] = offer
            # Keep supplier.reliability / lead in sync for directory & late delivery,
            # but do NOT copy absolute unit_price into base_price_multiplier —
            # that field is a relative market ratio in [~0.85, ~1.15].
            supplier = world.suppliers[sid]
            supplier.reliability = offer.reliability
            supplier.lead_time_days = offer.lead_time_days
            supplier.price_volatility = offer.price_volatility

        world.config.n_products = len(world.products)
        world.config.n_suppliers = len(world.suppliers)
        return world

    def get_offer(
        self, product_id: str, supplier_id: str
    ) -> Optional[SupplierOffer]:
        return self.offers.get(offer_key(product_id, supplier_id))

    def offers_for_product(self, product_id: str) -> List[SupplierOffer]:
        pid = str(product_id)
        return [o for (p, _), o in self.offers.items() if p == pid]

    def suppliers_for_product(self, product_id: str) -> List[VirtualSupplier]:
        """Active suppliers that have an offer for ``product_id``."""
        out: List[VirtualSupplier] = []
        for offer in self.offers_for_product(product_id):
            supplier = self.suppliers.get(offer.supplier_id)
            if supplier is None or supplier.is_defaulted:
                continue
            out.append(supplier)
        return out

    def lead_time_days_for_product(self, product_id: str) -> int:
        """Longest reachable lead time for ``product_id`` (0 if none)."""
        leads: List[int] = []
        if self.offers:
            for offer in self.offers_for_product(product_id):
                supplier = self.suppliers.get(offer.supplier_id)
                if supplier is None or supplier.is_defaulted:
                    continue
                leads.append(max(1, int(offer.lead_time_days)))
        else:
            for supplier in self.suppliers.values():
                if supplier.is_defaulted:
                    continue
                leads.append(max(1, int(supplier.lead_time_days)))
        return max(leads) if leads else 0

    # ---------------------------------------------------------------
    # Initialization
    # ---------------------------------------------------------------

    def _init_products(self) -> Dict[str, VirtualProduct]:
        products: Dict[str, VirtualProduct] = {}
        cfg = self.config
        for i in range(cfg.n_products):
            pid = f"product_{i:03d}"
            base_demand = self.rng.uniform(5.0, cfg.max_demand_per_day)
            products[pid] = VirtualProduct(
                product_id=pid,
                base_demand_per_day=base_demand,
                demand_volatility=self.rng.uniform(0.1, cfg.max_demand_volatility),
                holding_cost_per_unit=self.rng.uniform(0.5, 2.0),
                stockout_penalty_per_unit=self.rng.uniform(5, 20),
                current_stock=base_demand * self.rng.uniform(
                    cfg.min_initial_stock_days,
                    cfg.max_initial_stock_days,
                ),
                reorder_point=base_demand * self.rng.uniform(
                    cfg.min_reorder_days,
                    cfg.max_reorder_days,
                ),
            )
        return products

    def _init_suppliers(self) -> Dict[str, VirtualSupplier]:
        suppliers: Dict[str, VirtualSupplier] = {}
        cfg = self.config
        for i in range(cfg.n_suppliers):
            sid = f"supplier_{i:03d}"
            suppliers[sid] = VirtualSupplier(
                supplier_id=sid,
                reliability=self.rng.uniform(cfg.min_supplier_reliability, 0.99),
                base_price_multiplier=self.rng.uniform(0.85, 1.15),
                price_volatility=self.rng.uniform(0.02, cfg.max_price_volatility),
                lead_time_days=self.rng.randint(3, cfg.max_lead_time_days),
            )
        return suppliers

    # ---------------------------------------------------------------
    # Supplier persistence across quarters (spec section 26.6)
    # ---------------------------------------------------------------

    def export_supplier_state(self) -> Dict[str, VirtualSupplier]:
        """Deep-copied snapshot of the suppliers, for the next quarter's world.

        Copied rather than shared so that the next world cannot mutate the
        finished quarter's records, which the fitness evaluator still reads.
        """
        return {sid: copy.deepcopy(s) for sid, s in self.suppliers.items()}

    def carry_supplier_state(self, carried: Dict[str, VirtualSupplier]) -> None:
        """Replace freshly generated suppliers with ones from a previous quarter.

        Call immediately after construction and before the first ``tick()``.
        Only IDs this world already has are adopted, so changing
        ``n_suppliers`` between quarters shrinks or grows the roster rather
        than resurrecting counterparties the agent can no longer see.

        ``is_defaulted`` is deliberately reset: a default is a bad quarter, not
        a life sentence, and the agent needs the chance to observe recovery.
        """
        for sid, supplier in (carried or {}).items():
            if sid not in self.suppliers:
                continue
            adopted = copy.deepcopy(supplier)
            adopted.supplier_id = sid
            adopted.is_defaulted = False
            self.suppliers[sid] = adopted

    # ---------------------------------------------------------------
    # Sensory interface — agent observations (READ_ONLY analogue)
    # ---------------------------------------------------------------

    def observe_stock_levels(self) -> Dict[str, dict]:
        snapshot: Dict[str, dict] = {}
        for pid, p in self.products.items():
            lead = self.lead_time_days_for_product(pid)
            replenishment = product_replenishment_point(
                p.reorder_point,
                p.base_demand_per_day,
                p.demand_volatility,
                lead,
            )
            snapshot[pid] = {
                "quantity": round(p.current_stock, 2),
                "reorder_point": round(p.reorder_point, 2),
                "below_reorder_point": p.current_stock < p.reorder_point,
                "base_demand_per_day": float(p.base_demand_per_day),
                "demand_volatility": float(p.demand_volatility),
                "lead_time_days": int(lead),
                "replenishment_point": round(replenishment, 2),
                "below_replenishment_point": p.current_stock < replenishment,
            }
        return snapshot

    def observe_supplier_quote(
        self, supplier_id: str, product_id: str, qty: float
    ) -> dict:
        supplier = self.suppliers.get(supplier_id)
        if supplier is None or supplier.is_defaulted:
            return {"status": "unavailable", "supplier_id": supplier_id}

        offer = self.get_offer(product_id, supplier_id) if self.offers else None
        if self.offers and offer is None:
            return {
                "status": "unavailable",
                "supplier_id": supplier_id,
                "reason": "no_offer",
            }

        unit_price = self._quoted_unit_price(supplier, product_id, offer=offer)
        lead_time = offer.lead_time_days if offer is not None else supplier.lead_time_days
        reliability = offer.reliability if offer is not None else supplier.reliability
        safe_qty = safe_float(qty, 0.0)
        return {
            "status": "ok",
            "supplier_id": supplier_id,
            "product_id": product_id,
            "unit_price": round(unit_price, 4),
            "total_price": round(unit_price * safe_qty, 2),
            "lead_time_days": int(lead_time),
            "reliability_score": round(reliability, 3),
            "reputation": round(supplier.reputation, 3),
            "supplier_is_new": supplier.total_orders == 0,
        }

    def _quoted_unit_price(
        self,
        supplier: VirtualSupplier,
        product_id: str,
        *,
        offer: Optional[SupplierOffer] = None,
    ) -> float:
        """Deterministic per-(supplier, product, day) price noise.

        A dedicated Random seeded from a stable string key keeps quotes noisy
        across days while leaving ``self.rng`` untouched, so any number of
        observe_* calls leaves world state bit-identical.
        """
        if offer is not None:
            base = max(0.01, float(offer.unit_price))
            vol = float(offer.price_volatility)
        else:
            base = max(0.01, float(supplier.base_price_multiplier))
            vol = float(supplier.price_volatility)
        key = f"{self._quote_salt}|{supplier.supplier_id}|{product_id}|{self.day}"
        noise = max(0.5, random.Random(key).gauss(1.0, vol))
        return max(0.01, base * noise)

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
    # Motor interface — agent actions (write MCP tool analogue)
    # ---------------------------------------------------------------

    def place_order(self, supplier_id: str, product_id: str, qty: float) -> dict:
        """Analogue of MCP create_purchase_order.

        Executes immediately: the approval gate is deliberately absent in the
        sandbox because the money is virtual (spec section 0, principle 3).
        """
        if not is_finite_number(qty) or float(qty) <= 0:
            return {"status": "rejected", "reason": "invalid_quantity"}
        qty = float(qty)

        supplier = self.suppliers.get(supplier_id)
        if supplier is None:
            return {"status": "rejected", "reason": "unknown_supplier"}
        if supplier.is_defaulted:
            return {"status": "rejected", "reason": "supplier_defaulted"}
        if product_id not in self.products:
            return {"status": "rejected", "reason": "unknown_product"}

        quote = self.observe_supplier_quote(supplier_id, product_id, qty)
        if quote.get("status") != "ok":
            return {
                "status": "rejected",
                "reason": quote.get("reason") or "quote_unavailable",
            }
        total_cost = quote["total_price"]
        lead_time = int(quote.get("lead_time_days") or supplier.lead_time_days)

        if total_cost > self.budget:
            return {
                "status": "rejected",
                "reason": "insufficient_budget",
                "requested_cost": total_cost,
                "available_budget": round(self.budget, 2),
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
            arrival_day=self.day + lead_time,
        )
        self.pending_orders.append(order)
        return {
            "status": "accepted",
            "order_id": order.order_id,
            "cost": total_cost,
            "unit_price": quote["unit_price"],
            "eta_days": lead_time,
            "arrival_day": order.arrival_day,
        }

    # ---------------------------------------------------------------
    # World physics — independent of the agent
    # ---------------------------------------------------------------

    def tick(self) -> dict:
        """One simulated day. The agent never calls this — training_loop does."""
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
            offer = self.get_offer(order.product_id, order.supplier_id)
            reliability = (
                offer.reliability
                if offer is not None
                else (supplier.reliability if supplier is not None else 0.5)
            )
            on_time = True
            if supplier is not None and not supplier.is_defaulted:
                late_prob = self.config.late_delivery_probability_base * (
                    1.0 + (1.0 - reliability)
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
        for product in self.products.values():
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
    "OfferKey",
    "ProcurementWorld",
    "ProcurementWorldConfig",
    "SupplierOffer",
    "VirtualSupplier",
    "VirtualProduct",
    "PendingOrder",
    "offer_key",
    "product_replenishment_point",
]

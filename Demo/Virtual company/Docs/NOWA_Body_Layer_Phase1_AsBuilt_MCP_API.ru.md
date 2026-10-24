## Аннотация

English version: [NOWA_Body_Layer_Phase1_AsBuilt_MCP_API.en.md](NOWA_Body_Layer_Phase1_AsBuilt_MCP_API.en.md)

Документ от 18 августа 2026 года есть запись реализации фазы 1 и контракт интеграции MCP. Поставка включает описание органа `MCPCapability`, реестр на агента с индексом по типу действия, сенсорный кодировщик, затравщик с обязательным событием `ACTION`, абстрактный `MotorAdapter` и `ProcurementBodyMotorAdapter`, шлюз одобрения, жёсткие ограничения, петлю обратной связи, `MockMCPClient`, цикл `run_cycle` и `tick` вместе со `SleepScheduler`, роль `nowa_roles/procurement/` и лабораторный интерфейс. Пакет `nowa_body` не импортирует `nowa_sandbox`. Примечание от 24 августа 2026 года указывает, что обязательная точка расширения `MotorAdapter` заменена путём канонического A(t) и `SchemaBinder`; идентификатор инструмента, конверты и `ApprovalGate` настоящего документа остаются в силе. Когнитивный вызов `agent.step(..., decision_only=True)` о протоколе не знает, и ядро не импортирует SDK протокола.

Инварианты B1–B9 фиксируют реализованную границу. Адаптер не вызывает активацию гиппокампа, селектор и шаг агента. Каждый путь затравки и обратной связи содержит ровно одно событие `ACTION` и строится переприсваиванием. Бодрствующий цикл вызывает `decision_only=True`, если сигнатура это позволяет. Единственная точка исполнения записи — `ApprovalGate`. Сочетание `HIGH_WRITE` или `IRREVERSIBLE` с отключённым требованием одобрения даёт `HardConstraintViolation` в `route()`. Эпизод пишется после известного исхода автоисполнения или человеческого решения; `wait_and_monitor` и пустое предложение хранилище не пополняют. Частота сенсоров отделена от частоты шага: хозяин вызывает `tick()` около 1 Гц, обновление сенсоров по умолчанию раз в 300 с, и клиент транспорта хранится у шлюза, а не у runtime. Закрытый вопрос о процессе S сформулирован так: давление читается `get_sleep_pressure()` из `WakefulnessState._wakefulness`, атрибут агента называется `wakefulness`, рост идёт через `update_waking()`, и планировщик принимает оба имени атрибута. Краткое изложение намерения остаётся машинной строкой `_summarize()`.

Контракт транспорта — функция `(tool_id, params) -> dict` с обязательным полем `status`. Идентификатор имеет вид `mcp__<server>__<tool_name>` и после появления эпизодов не переименовывается, потому что обратная связь пишет его в гиппокамп. Успех со статусами `accepted`, `success` и `ok` даёт токен `result:success` и аффективный сдвиг валентности +0,4, возбуждения 0,2 и доверия 0,3. Отказ со статусами `rejected`, `failed` и `error` даёт `result:failure` и сдвиг валентности −0,4, возбуждения 0,5 и стресса 0,4. Прочее, включая отсутствие поля, есть `unknown` с пустым аффективным словарём. Исключения транспорта нормализуются в конверт ошибки и в цикл не пробрасываются, кроме нарушения жёсткого ограничения до исполнения. Таблица расхождений удерживает следующую фазу от возврата реализации к противоречащему псевдокоду: в частности, инициализация возможности не форсирует одобрение сама, а нарушение ловится на шлюзе.

---

# NOWA Body Layer — As-Built Фаза 1 и контракт MCP-интеграции

**Версия:** 1.0  
**Статус:** запись реализации и контракт интеграции  
**Дата:** 2026-08-18  
**Дополнение (2026-08-24).** Обязательная точка расширения `MotorAdapter`
заменена. Канонический путь A(t) и `SchemaBinder` изложен в
`NOWA_Body_Layer_AffectiveSpace_Body_Addendum.md` и
`Docs/spec_affective_space_platform_body.md`. Идентификатор `tool_id`, конверты и
`ApprovalGate` настоящего документа остаются в силе.

**Базовые документы:**
- `NOWA_Virtual_Employees_Architecture_Spec.md` (разделы 0–6)
- `NOWA_Body_Layer_Phase1_Spec.md` v1.0
- `NOWA_Body_Layer_Phase1_Patch_v1.1.md`
**Код:** `Demo/Virtual company/src/nowa_body/`, `nowa_roles/procurement/`
**Назначение этого документа:** зафиксировать *как реально реализовано*, и дать
стабильный контракт MCP-тулов для следующих интеграций (1С, email, CRM,
платёжный шлюз) с суверенным NOWA-агентом. Расхождения с псевдокодом
исходных спек помечены как **As-built**.

---

## 0. Что сделано в этой поставке (кратко)

Реализован универсальный слой «тело»: MCP-тул описывается как орган агента
(`MCPCapability`), регистрируется в per-agent реестре, читается через сенсорный
адаптер, исполняется только через `ApprovalGate`. Когнитивный контур
(`agent.step(..., decision_only=True)`) не знает про MCP.

| Область | Результат |
|---|---|
| Слой возможностей | `mcp_capability.py`, `risk_classifier.py`, `tool_registry.py` с индексом `action_type` |
| Сенсорика и затравка | `business_event_encoder.py`, `business_hippocampus_seeder.py` (урок 2: обязательное событие ACTION) |
| Моторика | абстрактный `MotorAdapter` + `ProcurementBodyMotorAdapter` |
| Управление | `approval_gate.py`, `hard_constraints.py`, `feedback_loop.py` |
| Транспорт для тестов | `mock_mcp.py` — READ + WRITE без сети |
| Исполнение | `run_cycle()` + `tick()` (кэш сенсоров) + `SleepScheduler` |
| Роль | `nowa_roles/procurement/` (корпус, классификатор, мотор) |
| Лаборатория | `nowa_body/gui_app.py`, `run_body_gui.bat` |
| Изоляция | `nowa_body` **не** импортирует `nowa_sandbox` |

**Q-Phase1-1a (закрыт):** Process S в ядре — `WakefulnessState._wakefulness`,
читается `get_sleep_pressure()`. Атрибут агента — `wakefulness` (не
`wakefulness_state`). Давление растёт только через `update_waking()`, не от
счётчика тиков. `SleepScheduler` читает оба имени атрибута.

**Q-Phase1-2 (реализован):** хост зовёт `tick()` ~1 Hz; сенсоры обновляются
раз в `sensor_refresh_interval_s` (по умолчанию 300 с).

**Q-Phase1-3:** `intent_summary` остаётся машинной строкой `_summarize()`;
NLG для UI отложен.

---

## 1. Принципы, которые интеграция не имеет права нарушать

Наследуются без изменений:

1. Агент — суверенная единица. Реестр тулов **per-agent**, транспорт MCP
   может быть общим.
2. Обучение только во сне. Waking-цикл тела использует
   `agent.step(..., decision_only=True)` и пишет эпизод **после** известного
   исхода.
   С #13: дневные исходы идут в лабильный слой, стабильные значения меняются только в `Agent.sleep()`; хост сотрудника передаёт `dt` ([issue-13-demo-virtual-company.ru.md](../../../Docs/specs/issue-13-demo-virtual-company.ru.md)).
3. Деньги / риск / approval — вне когнитивного контура. Агент не может
   «передумать» `ApprovalGate`.
4. MCP-тулы для агента — органы, не «интеграции». Ядро NOWA не импортирует
   MCP SDK.

Инварианты тела (as-built B1–B9):

| # | Правило |
|---|---|
| **B1** | `MotorAdapter.resolve()` не вызывает `hippocampus.activate`, selector, `agent.step` |
| **B2** | Каждый seed/feedback Path содержит ровно один `EventType.ACTION` |
| **B3** | `Path` строится переприсваиванием (`path = path.add_event(...)`) |
| **B4** | Runtime вызывает только `decision_only=True` (если сигнатура это позволяет) |
| **B5** | Единственная точка WRITE-execute — `ApprovalGate` (`mcp_executor`) |
| **B6** | `HIGH_WRITE` / `IRREVERSIBLE` + `requires_approval=False` → `HardConstraintViolation` в `route()` |
| **B7** | Feedback после известного исхода: auto-execute (`record.executed`) или human `decide()` |
| **B8** | `wait_and_monitor` / пустой `ProposedAction` не вызывает `hippocampus.store` |
| **B9** | Частота сенсоров развязана с частотой `agent.step` |

---

## 2. Граница: кто что делает

```
Хост (scheduler / GUI / будущий MCP-клиент)
    │  1. опрашивает READ-тулы (редко)
    │  2. собирает observations
    │  3. вызывает runtime.tick(sensor_fetcher)  или  run_cycle(observations)
    ▼
nowa_body.BusinessAgentRuntime
    │  encode_tool_result → context_events
    │  agent.step(context_events, decision_only=True) → action_type
    │  MotorAdapter.resolve → ProposedAction | None
    │  ApprovalGate.route
    │     ├── requires_approval=False → mcp_executor(tool_id, params)
    │     └── иначе → pending_queue (человек)
    ▼
mcp_executor: (tool_id: str, params: dict) -> dict
    │  As-built: MockMCPClient.execute
    │  Phase 3: реальный MCP transport (один на процесс, много агентов)
    ▼
внешний MCP-сервер (1С, email, …)
```

**As-built:** `BusinessAgentRuntime` **не** хранит MCP-клиент. Ссылка на
транспорт живёт только в `ApprovalGate.mcp_executor`. READ-опрос — обязанность
хоста (`sensor_fetcher`).

---

## 3. Контракт MCP Tools API (ядро интеграции)

Этот раздел — источник истины для подключения нового MCP-сервера к NOWA.
Реализация Phase 1 закрывает контракт через `MockMCPClient`; Phase 3
подменяет только транспорт, не поля capability и не форму result dict.

### 3.1 Идентификатор тула (`tool_id`)

Стабильная строка, уникальная в рамках агента (и желательно — глобально
в компании).

**Рекомендуемый формат:**

```
mcp__<server>__<tool_name>
```

Примеры:

| tool_id | server_name | смысл |
|---|---|---|
| `mcp__1c__get_stock_levels` | `1c_erp` | сенсор остатков |
| `mcp__1c__create_purchase_order` | `1c_erp` | мышца заказа |
| `mcp__email__send` | `email` | мышца письма |

Правила:

- `tool_id` — ключ реестра и аргумент `mcp_executor`.
- Сегмент после последнего `__` используется fallback-классификатором
  событий (`encode_tool_result` без role classifier).
- Не переименовывать `tool_id` после появления эпизодов: feedback пишет
  `action:<tool_id>` в гиппокамп.

### 3.2 Транспортный вызов (единственная точка I/O)

```text
mcp_executor(tool_id: str, params: dict) -> dict
```

Это **единственная** сигнатура, которую знает тело.

| Аргумент | Тип | Требование |
|---|---|---|
| `tool_id` | `str` | Точное совпадение с `MCPCapability.tool_id` |
| `params` | `dict` | JSON-совместимый объект (ключи-строки). Пустой `{}` допустим для READ без фильтров |

**Возврат всегда `dict`.** As-built `MockMCPClient.execute` и
`ApprovalGate._invoke_executor` нормализуют сбои в dict и **не пробрасывают**
исключение в runtime (кроме `HardConstraintViolation` до execute).

Интегратор реального MCP обязан:

1. Сериализовать MCP JSON-RPC / SDK result в `dict`.
2. Поймать timeout/сеть и вернуть envelope ошибки (см. 3.3).
3. Не возвращать `None`, list, str на верхнем уровне.

### 3.3 Envelope результата (обязательное поле `status`)

Тело **не парсит** доменную бизнес-схему 1С внутри encoder исхода. Исход
действия читается так:

```text
status = str(result["status"]).strip().lower()
```

| Класс | Значения `status` (as-built) | Токены эпизода | Affect |
|---|---|---|---|
| Успех | `accepted`, `success`, `ok` | `result:success` | valence +0.4, arousal 0.2, trust 0.3 |
| Отказ | `rejected`, `failed`, `error` | `result:failure` | valence −0.4, arousal 0.5, stress 0.4 |
| Прочее | любое другое, в т.ч. отсутствие поля → `unknown` | `result:unknown` | `{}` |

Рекомендуемый канонический envelope для **любого** тула:

```json
{
  "status": "ok",
  "reason": null,
  "...": "доменные поля"
}
```

Ошибки транспорта (as-built нормализация):

| Ситуация | Envelope |
|---|---|
| Неизвестный `tool_id` | `{"status": "error", "reason": "unknown_tool:<id>"}` |
| `TimeoutError` | `{"status": "error", "reason": "timeout:<exc>"}` |
| Прочее исключение тула | `{"status": "error", "reason": "tool_error:<exc>"}` |
| Не-dict от тула | `{"status": "error", "reason": "non_dict_result", "value": ...}` |
| Исключение executor в gate | `{"status": "error", "reason": "executor_error:<exc>"}` |

**Правило для интегратора:** не бросать из executor в Phase 3, если можно
вернуть envelope. Тогда `apply_feedback_to_agent` всегда видит `status` и
агент учится на реальном исходе, а не на падении хоста.

Доменные поля (остатки, id заказа, текст письма) живут **рядом** со `status`,
не вместо него.

### 3.4 READ и WRITE

| Класс | `CapabilityRisk` | Кто вызывает | Когда |
|---|---|---|---|
| Сенсор | `READ_ONLY` | **хост** (`sensor_fetcher`) | раз в `sensor_refresh_interval_s` или по webhook |
| Мышца | любой не-`READ_ONLY` | **только** `ApprovalGate` | после `MotorAdapter.resolve` и (если надо) человека |

Сенсорные вызовы **не** идут через `ApprovalGate` в текущем runtime: хост
опрашивает READ сам и кладёт payload в `observations["tool_results"]`.
Это сознательное разделение: approval — барьер денег/мутации мира, не барьер
зрения.

`requires_approval=False` для `READ_ONLY` — нормальная конфигурация Stage 2.

`requires_approval=False` для `HIGH_WRITE` / `IRREVERSIBLE` — **запрещено**
(B6). Для `MEDIUM_WRITE` на Stage 2 по умолчанию `True`.

### 3.5 `MCPCapability` — паспорт органа

Файл: `nowa_body/mcp_capability.py`.

```text
MCPCapability
  tool_id:                str              # §3.1
  server_name:            str              # логическое имя сервера, не URL
  display_name:           str              # для человека / UI
  description:            str              # для эвристики риска и оператора
  risk_level:             CapabilityRisk
  domain_tags:            List[str]        # ["procurement"], ["finance"], …
  input_schema:           Dict[str, Any]   # JSON Schema (рекомендуется)
  output_schema:          Dict[str, Any]   # JSON Schema (рекомендуется)
  requires_approval:      bool = True
  cost_impact_estimate:   Optional[str]    # "none"|"low"|"medium"|"high"
  max_autonomous_value:   Optional[float]  # порог автономии Stage 3
  action_types:           List[str]        # метки ActionSelector
```

**As-built отличие от родительской спеки:** `__post_init__` **не** переписывает
`requires_approval=True` для WRITE. Невалидная комбинация представима как
данные и ловится `assert_stage2_invariant` в `ApprovalGate.route` — иначе
тест «HIGH_WRITE нельзя обойти» был бы мёртвым кодом.

#### 3.5.1 `action_types` — мост мозг → мышца

NOWA выбирает **лейбл стратегии**, не `tool_id`.

Примеры:

| action_type (мозг) | типичный tool_id (тело) |
|---|---|
| `place_order_reliable_supplier` | `mcp__1c__create_purchase_order` |
| `urgent_reorder` | тот же WRITE-тул, другие params |
| `notify_supplier_urgent` | `mcp__email__send` |
| `wait_and_monitor` | **нет тула** — motor возвращает `None` |

Один тул может закрывать несколько `action_types`. Несколько тулов на один
`action_type` допустимы: `MotorAdapter` выбирает **лексикографически
минимальный** `tool_id`. Роль с несколькими эквивалентными тулами должна
приоритизировать регистрацией / отдельными `action_types`, не рассчитывать
на случайность.

`wait_and_monitor` **не** регистрируется как `action_type` WRITE-тула.

#### 3.5.2 `CapabilityRisk`

| Значение enum | строка | смысл | Stage 2 |
|---|---|---|---|
| `READ_ONLY` | `read_only` | чтение мира | обычно без approval |
| `LOW_WRITE` | `low_write` | черновик, не отправлен | approval по флагу |
| `MEDIUM_WRITE` | `medium_write` | письмо, заявка, документ | approval по умолчанию |
| `HIGH_WRITE` | `high_write` | деньги, цена контракта | **всегда** approval |
| `IRREVERSIBLE` | `irreversible` | удаление, финальная сделка | **всегда** approval |

### 3.6 Эвристика риска (только default)

`classify_risk_heuristic(tool_name, description="") -> CapabilityRisk`

Порядок: IRREVERSIBLE → HIGH → MEDIUM → LOW → READ. Неизвестный паттерн →
`HIGH_WRITE` (безопасный отказ). Сначала имя, затем description.

**Нельзя** отдавать агенту HIGH/IRREVERSIBLE, классифицированные только
эвристикой, без человеческого review.

Ключевые подстроки (as-built):

- READ: `get_`, `list_`, `search_`, `read_`, `fetch_`, `query_`, `check_`, `view_`
- LOW: `draft_`, `prepare_`, `compose_`, `generate_document_`
- MEDIUM: `send_`, `create_order_`, `submit_`, `post_`, `update_`
- HIGH: `pay_`, `transfer_`, `approve_payment_`, `sign_contract_`, `change_price_`
- IRREVERSIBLE: `delete_`, `cancel_contract_`, `terminate_`, `revoke_`

`register_from_mcp_discovery` в Phase 1 — `NotImplementedError`. Phase 3:
обнаружение инструментов MCP → эвристика → **ручное подтверждение** → `register()`.

### 3.7 Реестр: суверенный срез, общий транспорт

```text
MCPToolRegistry(agent_id)
  register(capability)
  get(tool_id) -> Optional[MCPCapability]
  list_all() / list_by_risk / list_by_domain
  sensory_capabilities()   # только READ_ONLY
  motor_capabilities()     # всё, что не READ_ONLY
  capabilities_for_action(action_type) -> List[MCPCapability]
```

Повторный `register` с тем же `tool_id` заменяет паспорт и перестраивает
индекс `action_type`.

Два агента на одном 1С-сервере:

```
shared:   MCP transport / MockMCPClient
agent_A:  registry {get_stock_levels, create_purchase_order}
agent_B:  registry {get_invoices, post_payment}
```

Видимость задаётся `register()`, не сетевым ACL транспорта (ACL — дополнительная
защита, не замена суверенности).

### 3.8 JSON Schema входа/выхода

`input_schema` / `output_schema` в Phase 1 **не валидируются** автоматически.
Для Phase 3 интегратор **обязан** заполнить их при регистрации: это контракт
для MotorAdapter и для человека в approval UI.

Рекомендуемый профиль: JSON Schema draft-07, `type: object`, без `$ref` на
внешние URL.

MotorAdapter роли строит `tool_params` так, чтобы они удовлетворяли
`input_schema`. Gate передаёт params в executor **как есть** (после optional
modify человеком).

### 3.9 Снапшот наблюдений (`observations`) — вход runtime

Хост собирает dict **до** `run_cycle` / внутри `sensor_fetcher` для `tick()`.

Каноническая форма (as-built, роль procurement понимает оба слоя):

```json
{
  "agent_id": "buyer_001",
  "affect_snapshot": {},
  "stock": { "<product_id>": { "...поля остатка..." } },
  "suppliers": { "<supplier_id>": { "...поля поставщика..." } },
  "budget": { "remaining": 8000.0, "utilization_ratio": 0.35 },
  "tool_results": {
    "mcp__1c__get_stock_levels": { "status": "ok", "stock": { } },
    "mcp__1c__get_suppliers": { "status": "ok", "suppliers": { } },
    "mcp__1c__get_budget": { "status": "ok", "remaining": 8000.0, "utilization_ratio": 0.35 }
  }
}
```

Правила:

- `tool_results`: карта `tool_id → envelope` (§3.3). Runtime кодирует **только**
  эту карту в `context_events`. Пустая карта → токен `quiet_period`.
- Верхний уровень `stock` / `suppliers` / `budget` — нормализованный вид для
  `ProcurementBodyMotorAdapter`. Если его нет, адаптер пытается вытащить
  вложенности из `tool_results` по иглам в `tool_id` (`stock`, `supplier`,
  `budget`) и ключам `stock|products|stock_levels`, `suppliers|supplier_directory`.
- `agent_id` копируется в `ProposedAction.agent_id`.
- `affect_snapshot` копируется в `ProposedAction.affective_context` (не
  инжектируется в `affective_space` на этапе solve).

Для новой роли: либо класть нормализованные ключи, либо учить свой MotorAdapter
читать свои ключи из `tool_results`. Encoder мира агента зависит только от
`tool_results` + `event_classifier`.

### 3.10 Сенсорный адаптер: результат MCP → `context_events`

`BusinessEventEncoder.encode_tool_result(tool_id, result, event_classifier=None)`

1. Если передан `event_classifier(tool_id, result) -> List[str]` и он вернул
   непустой список имён событий — используются они.
2. Иначе имя события = последний сегмент `tool_id` после `__`.
3. Для каждого имени: токены `event:<name>` + valence/arousal/domain из
   `affective_mapping`, если имя есть в карте.

Классификатор — **роль-специфичен**. Закупки: `classify_procurement_events`
(остаток ниже ROP → `stock_critical_low`, defaulted → `supplier_defaulted`,
и т.д.). Бухгалтерия получит свой модуль. Универсальный encoder не знает 1С.

`encode_action_outcome(action_type, tool_result)` смотрит **только** `status`
(§3.3). `action_type` зарезервирован для ролевых энкодеров; as-built не
используется. ACTION-событие в Path добавляет **caller** (`feedback_loop`):
`action:<proposed_action.tool_id>`.

### 3.11 Motor Adapter: ActionIntent → `ProposedAction`

`ProposedAction` (ещё не вызов MCP):

| Поле | Смысл |
|---|---|
| `action_id` | UUID, ключ очереди approval |
| `agent_id` | кто предложил |
| `tool_id` | какой орган вызвать |
| `tool_params` | аргументы `mcp_executor` |
| `risk_level` | копия с capability |
| `requires_approval` | копия с capability |
| `intent_summary` | строка для лога / будущего UI |
| `affective_context` | снимок на момент решения |
| `estimated_cost_impact` | optional float |

`resolve()` никогда не бросает: мусорные observations → `None`.
`wait_and_monitor` / неизвестный action_type без capability → `None`.

Базовый класс `_build_params` — `NotImplementedError` (ловится, → `None`).
Роль обязана реализовать сбор params.

### 3.12 ApprovalGate: маршрут WRITE

```text
route(proposed) -> ApprovalRecord
decide(action_id, decision, decided_by, rejection_reason?, modified_params?) -> ApprovalRecord
expire_stale() -> List[ApprovalRecord]
```

`ApprovalStatus`: `pending | approved | rejected | modified | expired`.

Поведение `route`:

1. Собрать capability: lookup по `tool_id` **или** поля `ProposedAction`.
2. Взять **более опасный** уровень риска из реестра и из предложенного действия; `requires_approval`
   = OR двух флагов (proposed не может «опустить» флаг реестра).
3. `assert_stage2_invariant`.
4. Если не требуется approval → немедленный `mcp_executor`, `executed=True`,
   `decided_by="system:read_only_auto"`.
5. Иначе запись в `pending_queue`, optional `notification_channel(record)`.

`decide`:

- `APPROVED` / `MODIFIED` → execute, `executed=True`.
- `MODIFIED` мержит `modified_params` в `tool_params`.
- `REJECTED` → без execute, `executed=False`.
- Нет id в очереди → `KeyError`.

Runtime `complete_approval` после `decide` вызывает feedback, если статус
уже не `PENDING` (включая reject: исход — решение человека).

Таймаут очереди: `approval_timeout_hours` (default 48), `expire_stale()`.
Expired не исполняется; reward as-built −0.2.

### 3.13 Feedback → гиппокамп (после исхода)

`approval_to_reward`:

| status | reward |
|---|---|
| APPROVED | +1.0 |
| MODIFIED | +0.4 |
| REJECTED | −1.0 |
| EXPIRED | −0.2 |
| иначе | 0.0 |

Path: CONTEXT-токены из `encode_action_outcome` + один ACTION
`action:<tool_id>` + CONSEQUENCE `approved` если reward>0 иначе `rejected`.

Affect: `affective_space.step(inputs=...)`, если есть.

### 3.14 Процедура подключения нового MCP-сервера (чеклист Phase 3)

1. Получить список tools с сервера (MCP `tools/list`).
2. Для каждого tool:
   - назначить стабильный `tool_id` (`mcp__<server>__<name>`);
   - заполнить `input_schema` / `output_schema` из MCP `inputSchema`;
   - прогнать `classify_risk_heuristic`, **затем** человек подтверждает
     `risk_level` и `requires_approval`;
   - назначить `action_types` из лексикона роли (не из имени тула вслепую);
   - проставить `domain_tags`.
3. Зарегистрировать **срез** в `MCPToolRegistry` конкретного агента.
4. Реализовать `mcp_executor` = тонкая обёртка SDK: всегда `dict` + `status`.
5. Хост: READ-тулы в `sensor_fetcher` с интервалом ≠ 1 Hz.
6. Роль: `event_classifier` + subclass `MotorAdapter._build_params`.
7. Прогнать: pending HIGH/MEDIUM write; B6 probe; timeout envelope;
   `wait_and_monitor` не пишет эпизоды.

---

## 4. Референс: тулы лабораторной роли «закупщик» (MockMCP)

Это **не** финальный 1С-контракт, а эталон формы, которую 1С-адаптер должен
повторить или явно замапить.

### 4.1 `mcp__1c__get_stock_levels` — сенсор

| | |
|---|---|
| risk | `READ_ONLY`, `requires_approval=False` |
| action_types | `[]` (хост, не мозг) |
| params | `{}` (фильтры — будущее) |

**Выход (as-built lab):**

```json
{
  "status": "ok",
  "stock": {
    "sku_a": {
      "quantity": 0.0,
      "reorder_point": 40.0,
      "below_reorder_point": true,
      "base_demand_per_day": 1.5,
      "projected_quantity": 0.0
    }
  }
}
```

Поля, которые понимает `ProcurementBodyMotorAdapter` (любое подмножество):

- количество: `quantity`, плюс inbound `inbound` / `inbound_quantity`, либо
  сразу `projected` / `projected_quantity`
- точка заказа: `reorder_point`, `replenishment_point`, флаги
  `below_reorder_point` / `below_replenishment_point` /
  `projected_below_replenishment_point`
- спрос: `base_demand_per_day` → qty = спрос × 30 дней

Классификатор: любой SKU ниже точки → событие `stock_critical_low`.

### 4.2 `mcp__1c__get_suppliers` — сенсор

```json
{
  "status": "ok",
  "suppliers": {
    "acme": {
      "reliability": 0.95,
      "unit_price": 8.0,
      "lead_time_days": 3,
      "reputation": 0.9,
      "is_defaulted": false,
      "status": "active",
      "offers": {
        "sku_a": {
          "unit_price": 8.0,
          "reliability": 0.95,
          "lead_time_days": 3
        }
      }
    }
  }
}
```

Синонимы, которые читает motor:

- цена: `unit_price` | `base_price` | `price` | `base_price_multiplier`
- срок: `lead_time_days` | `lead_time`
- надёжность: `reliability` | `reliability_score`
- оферты: `offers` | `product_offers` (dict или list с `product_id`)
- недоступен: `is_defaulted=true`, `available=false`, `status` ∈
  `{unavailable, defaulted, inactive}`

`is_defaulted` / status defaulted → событие `supplier_defaulted`.

### 4.3 `mcp__1c__get_budget` — сенсор

```json
{
  "status": "ok",
  "remaining": 8000.0,
  "utilization_ratio": 0.35
}
```

Motor ограничивает qty: `floor(remaining / unit_price, 1 знак)`.
`remaining <= 0` или `utilization_ratio > 0.9` → `budget_exceeded`.

### 4.4 `mcp__1c__create_purchase_order` — мышца

| | |
|---|---|
| risk | `MEDIUM_WRITE` |
| requires_approval | `True` на Stage 2 (лабораторная галка auto-execute — только для отладки, сброс сессии) |
| action_types | `place_order_reliable_supplier`, `place_order_cheap_supplier`, `urgent_reorder`, `diversify_supplier` |

**Вход (`tool_params` as-built):**

```json
{
  "supplier_id": "acme",
  "product_id": "sku_a",
  "qty": 45.0,
  "strategy": "place_order_reliable_supplier",
  "confidence": 0.95
}
```

`strategy` / `confidence` — метаданные решения; 1С может их игнорировать,
но полезно писать в audit.

**Выход:**

```json
{
  "status": "accepted",
  "params": { "supplier_id": "acme", "product_id": "sku_a", "qty": 45.0 }
}
```

Лаборатория эмулирует также `rejected` / `timeout` / `error` тем же envelope
(timeout → `status=error`, `reason` содержит `timeout:`).

Стратегии выбора поставщика (тело, не мозг):

| action_type | правило |
|---|---|
| `place_order_reliable_supplier` | max reliability |
| `place_order_cheap_supplier` | min price (fallback: min reputation) |
| `urgent_reorder` | min lead_time (fallback: max reputation) |
| `diversify_supplier` | min упоминаний `supplier:<id>` в `hippocampus.experiences` (read-only) |

Нет SKU ниже ROP, нет доступного поставщика, qty после cap = 0 → `resolve`
возвращает `None` (тик без WRITE).

---

## 5. Runtime API хоста

### 5.1 `BusinessAgentRuntime`

```text
tick(sensor_fetcher, *, now=None) -> dict
run_cycle(observations, *, now=None) -> dict
complete_approval(action_id, decision, decided_by="human",
                  rejection_reason=None, modified_params=None) -> ApprovalRecord
```

`tick`: если интервал сенсоров истёк — `sensor_fetcher()`; иначе кэш.
Ключ результата `sensor_refreshed: bool`.

`run_cycle`: чистый проход на готовом снапшоте (тесты, песочница).

Общие ключи результата:

| Ключ | Когда |
|---|---|
| `action_type` | всегда |
| `context_events` | всегда |
| `proposed` | `ProposedAction` или `None` |
| `approval_status` | если был proposed |
| `executed` | если был proposed |
| `record` | `ApprovalRecord` если был proposed |
| `slept` | bool |
| `sleep_reason` | `"circadian"` \| `"fatigue"` \| `""` |
| `sensor_refreshed` | только после `tick()` |

Sleep: `SleepScheduler` (окно часов default 02:00–05:00, порог Process S
0.85, анти-thrash `min_ticks_between_sleep` default 3600). После сна —
`mark_slept()`. Хост лабораторный может ставить `min_ticks=0`.

`simulated_tick_seconds`: явный `update_waking(elapsed)` для тестов; в живом
1 Hz достаточно wall-clock внутри `Agent.step` + no-op второго вызова.

### 5.2 Вызов ядра NOWA

```text
agent.step(context_events: List[str], decision_only=True) -> str | intent
```

Runtime достаёт строку из `str` либо атрибутов `action_type|action|label|name`.
Иначе `wait_and_monitor`.

Эпизод в гиппокамп из `step()` **не** пишется (decision_only). Пишет тело
после MCP/человека.

---

## 6. Карта модулей as-built

```
src/nowa_body/          # универсальное тело, без nowa_sandbox
  mcp_capability.py
  risk_classifier.py
  tool_registry.py
  business_event_encoder.py
  business_hippocampus_seeder.py
  motor_adapter.py
  approval_gate.py
  hard_constraints.py
  feedback_loop.py
  mock_mcp.py
  sleep_scheduler.py
  runtime.py
  lab_session.py        # headless лаборатория (не часть __init__)
  gui_app.py / gui_i18n.py
src/nowa_roles/procurement/
  motor_adapter.py      # ProcurementBodyMotorAdapter
  seed_corpus.py
  event_classifier.py
```

Публичный импорт пакета (`nowa_body.__init__`) не тянет GUI и роли.

Запуск лаборатории: `Demo/Virtual company/run_body_gui.bat`.

---

## 7. Расхождения as-built с псевдокодом исходных спек

| Тема | Спека v1.0 / parent | As-built |
|---|---|---|
| `MCPCapability.__post_init__` | форсирует approval на MEDIUM+ | не форсирует; ловит B6 на gate |
| `ApprovalGate` lookup | только поля proposed | lookup реестра + max(risk) + OR(approval) |
| Место пакетов | `nowa_body/tests/` | `Demo/Virtual company/tests/` (как sandbox) |
| `nowa_governance/*` | отдельные пакеты | внутри `nowa_body` |
| `register_from_mcp_discovery` | «под SDK» | `NotImplementedError` до Phase 3 |
| Executor exceptions | не специфицированы | всегда нормализуются в `{status: error}` |
| Feedback на reject | B7 «только executed» vs parent 6.4 | `route`: только executed; `complete_approval`: любой терминальный decide |
| Сон | открытый Q | `SleepScheduler` + `tick()` |

Эти строки — чеклист, чтобы Phase 3 не «исправляла» as-built обратно в
противоречивый псевдокод.

---

## 8. Минимальный пример интеграции (псевдокод хоста)

```python
registry = MCPToolRegistry(agent_id="buyer_001")
registry.register(stock_cap)          # READ_ONLY
registry.register(order_cap)          # MEDIUM_WRITE + action_types

def mcp_executor(tool_id: str, params: dict) -> dict:
    # SDK call → всегда dict с полем status
    ...

gate = ApprovalGate(
    mcp_executor=mcp_executor,
    capability_lookup=registry.get,
    notification_channel=notify_human,  # Slack/UI
)

runtime = BusinessAgentRuntime(
    agent=nowa_agent,
    tool_registry=registry,
    motor_adapter=ProcurementBodyMotorAdapter(registry),
    approval_gate=gate,
    encoder=BusinessEventEncoder(affective_mapping),
    event_classifier=classify_procurement_events,
    sensor_refresh_interval_s=300.0,
)

def fetch_sensors() -> dict:
    stock = mcp_executor("mcp__1c__get_stock_levels", {})
    suppliers = mcp_executor("mcp__1c__get_suppliers", {})
    budget = mcp_executor("mcp__1c__get_budget", {})
    return {
        "agent_id": "buyer_001",
        "stock": stock.get("stock", {}),
        "suppliers": suppliers.get("suppliers", {}),
        "budget": budget,
        "tool_results": {
            "mcp__1c__get_stock_levels": stock,
            "mcp__1c__get_suppliers": suppliers,
            "mcp__1c__get_budget": budget,
        },
    }

# ~1 Hz
runtime.tick(fetch_sensors)

# когда человек нажал Approve в UI
runtime.complete_approval(action_id, ApprovalStatus.APPROVED, decided_by="ivan")
```

---

## 9. Открыто для следующих фаз

| ID | Тема |
|---|---|
| Phase 2 | человеческий approval UI (Slack/email); NLG `intent_summary` (Q-Phase1-3) |
| Phase 3 | реальный MCP SDK в `mcp_executor`; `register_from_mcp_discovery` + human review |
| Phase 3 | валидация `tool_params` по `input_schema` до execute |
| Roles | sales / accounting: свой seed corpus, classifier, MotorAdapter |
| Security | сетевой ACL MCP в дополнение к per-agent registry |

---

*As-built Фаза 1 + контракт MCP Tools API v1.0. Готов как входной документ
для интеграций с агентом NOWA. Код в `nowa_body` имеет приоритет при расхождении
с псевдокодом Phase1 Spec v1.0.*

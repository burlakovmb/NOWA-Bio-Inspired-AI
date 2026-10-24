"""English / Russian UI strings for the Role Configurator."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_LANG = "en"
SUPPORTED = ("en", "ru")
FLAG_EN = "\U0001F1EC\U0001F1E7"
FLAG_RU = "\U0001F1F7\U0001F1FA"

STRINGS: Dict[str, Dict[str, str]] = {
    "en": {
        "app.title": "NOWA Role Configurator",
        "cli.description": "NOWA role configurator",
        "cli.lang_help": "UI language. Overrides NOWA_LANG and the saved preference.",
        "lang.en": "EN",
        "lang.ru": "RU",
        "list.heading": "Company roles",
        "list.empty": "No roles found in nowa_roles/",
        "list.meta": "{domain} · {tools} tools · {lessons} lessons · changed {when}",
        "list.new": "+ New role",
        "list.open": "Open role",
        "list.back": "← Roles",
        "emp.heading": "Employees",
        "emp.empty": "No employees yet. Create one to start a mind.",
        "emp.new": "+ New employee",
        "emp.open": "Open",
        "emp.delete": "Delete",
        "emp.start": "Start",
        "emp.stop": "Stop",
        "emp.restart": "Restart",
        "emp.back": "← Employees",
        "emp.roles_line": "roles: {roles}",
        "emp.rhythm_line": "tick {tick}s · sleep ≥ {sleep}",
        "emp.pending": "pending: {n}",
        "emp.status.stopped": "stopped",
        "emp.status.starting": "starting",
        "emp.status.running": "running",
        "emp.status.sleeping": "sleeping",
        "emp.status.awaiting_approval": "awaiting approval",
        "emp.status.stopping": "stopping",
        "emp.status.error": "error",
        "emp.new.title": "New employee",
        "emp.new.name": "Name",
        "emp.new.id": "id",
        "emp.new.roles": "Roles (at least one, only valid ones):",
        "emp.new.rhythm": "Rhythm",
        "emp.new.tick": "Tick (seconds)",
        "emp.new.sleep": "Sleep no more often than (seconds)",
        "emp.new.create": "Create",
        "emp.new.cancel": "Cancel",
        "emp.roles": "Roles",
        "emp.add_role": "+ add role",
        "emp.tick": "Tick",
        "emp.sensor": "Sensor poll",
        "emp.sleep_min": "Sleep no more often than",
        "emp.sleep_window": "Sleep window (hours)",
        "emp.fatigue": "Fatigue threshold",
        "emp.seconds": "s",
        "emp.mcp": "MCP",
        "emp.organs": "Organs: {read} READ / {write} WRITE · last sensor {when}",
        "emp.memory": "Memory: checkpoint {when} · {n} episodes",
        "emp.stale": "Roles changed after start — restart the employee to pick up the new YAML.",
        "emp.approval": "Approval queue",
        "emp.alerts": "Not sent: business limits ({n})",
        "emp.alerts_clear": "Clear",
        "emp.alerts_badge": "⚠ not sent: {n}",
        "emp.alert_line": "{at}  {limit}: {summary} — {reason}",
        "emp.alert_reason.nothing_left": "nothing left",
        "emp.alert_reason.over_available": "not enough for one unit (left {available})",
        "emp.approve": "Approve",
        "emp.reject": "Reject",
        "emp.edit_params": "Edit params",
        "emp.write_failed": "The write did not create a document.\n{status}: {detail}",
        "emp.write_ok": "Document created: {number}",
        "emp.qty_zero_confirm": "qty is 0 — Drive will likely reject the order. Approve anyway?",
        "emp.log": "Tick log (tail)",
        "emp.narrative": "Memory (narrative)",
        "emp.reset_memory": "Reset memory",
        "emp.reset_confirm": "Delete this employee's mind checkpoint and sidecar? The next Start will seed intuition if that is enabled.",
        "emp.delete_confirm": "Delete employee «{name}» and their memory? If they are running they will be stopped first. This cannot be undone.",
        "emp.close_running": "Stop {n} employee(s) and save memory?",
        "emp.close_title": "Running employees",
        "emp.sleep_zero_confirm": "Sleep interval 0 allows sleep on every tick and will break learning. Continue?",
        "emp.sleep_hint": "Tick is how often the employee looks at the world. Sleep is how often they consolidate experience. Sleeping every tick will break learning.",
        "emp.none": "—",
        "emp.ago": "{n}s ago",
        "status.valid": "valid",
        "status.warnings": "{n} warnings",
        "status.error": "invalid",
        "new.title": "New role",
        "new.display_name": "Display name",
        "new.create": "Create",
        "new.cancel": "Cancel",
        "tab.servers": "MCP servers",
        "tab.tools": "Tools",
        "tab.vocab": "Action vocabulary",
        "tab.affect": "Affective mapping",
        "tab.seed": "Seed corpus",
        "tab.validation": "Validation & preview",
        "tab.dryrun": "Dry run",
        "wizard.banner": "New role wizard — step {step} of 6. After this, tabs unlock.",
        "wizard.next": "Next →",
        "wizard.back": "← Back",
        "wizard.finish": "Finish wizard",
        "servers.intro": (
            "Each employee connects to one or more MCP servers. "
            "Tools belong to a server and stay nested under it."
        ),
        "servers.add": "+ Add MCP server",
        "servers.empty": (
            "No MCP servers yet. Add a server here — then attach its tools on the next tab."
        ),
        "servers.id": "Server id (e.g. 1c_erp)",
        "servers.display": "Display name",
        "servers.transport": "Transport",
        "servers.enabled": "Enabled",
        "servers.command": "Command (stdio)",
        "servers.args": "Arguments",
        "servers.url": "URL (sse / http)",
        "servers.username": "Username",
        "servers.password": "Password",
        "servers.tools_count": "{catalog} tools on this server · {included} in the role",
        "servers.tools_count_no_catalog": (
            "{included} in the role · catalog not loaded — Discover tools"
        ),
        "servers.remove": "Remove server",
        "servers.remove_confirm": (
            "Remove server “{server}” and all of its tools from this role?"
        ),
        "servers.title": "New MCP server",
        "servers.placeholder": (
            "For http / sse fill URL and, if the publication requires it, "
            "username and password (empty password is allowed). "
            "Then use Discover tools on the Tools tab. stdio arrives later."
        ),
        "tools.discover": "Discover tools",
        "tools.discover_done": "Found {n} tools on this server ({included} already in the role).",
        "tools.add_manual": "+ Add tool manually",
        "tools.server": "Server",
        "tools.risk": "Risk",
        "tools.approval": "Requires approval",
        "tools.approval_auto_off": "auto, off",
        "tools.approval_locked": "Required (cannot turn off)",
        "tools.heuristic": "suggested by heuristic",
        "tools.confirm_risk": "Confirm risk",
        "tools.decisions": "Decisions",
        "tools.add_decision": "+ add decision",
        "tools.tags": "Tags",
        "tools.add_tag": "+ tag",
        "tools.not_included": "Not included in the role — irreversible-risk tool",
        "tools.high_note": (
            "* HIGH_WRITE / IRREVERSIBLE cannot run without human approval — "
            "architectural limit (assert_stage2_invariant), not a setting."
        ),
        "tools.included": "Include in role",
        "tools.poll": "Poll as sensor",
        "tools.poll_defaults": "Poll defaults (required fields)",
        "tools.poll_write": "Write tools cannot be polled",
        "tools.no_server": "Add an MCP server on the previous tab first.",
        "tools.go_servers": "Go to MCP servers",
        "manual.title": "Add tool manually",
        "manual.tool_id": "tool_id",
        "manual.display": "Display name",
        "manual.description": "Description",
        "manual.server": "Server",
        "vocab.intro": "Which decisions can this employee take?",
        "vocab.add": "+ Add decision",
        "vocab.add_title": "Add a decision",
        "vocab.name_label": "What is this decision called?",
        "vocab.name_hint": "A short name the employee would recognise, e.g. “Urgent reorder”.",
        "vocab.desc_label": "What does the employee actually do?",
        "vocab.desc_hint": "One or two sentences in plain language. The technical code is created automatically.",
        "vocab.add_confirm": "Add",
        "vocab.source_label": "Where does this decision come from?",
        "vocab.from_adapter": "Choose a WRITE organ already registered on this role",
        "vocab.from_custom": "Describe a new decision (it must match a WRITE tool_id)",
        "vocab.adapter_pick": "Available WRITE organs",
        "vocab.adapter_empty": "Every WRITE organ is already in the list.",
        "decision.mcp__1c__create_purchase_order": "Create purchase order",
        "decision.mcp__1c__create_purchase_order.desc": "Place a purchase order from current stock and suppliers.",
        "decision.mcp__drivemcp__create_purchase_order": "Create purchase order",
        "decision.mcp__drivemcp__create_purchase_order.desc": "Place a purchase order from current stock and suppliers.",
        "decision.urgent_reorder": "Urgent reorder",
        "decision.urgent_reorder.desc": "Order from the fastest supplier, regardless of price.",
        "decision.place_order_reliable_supplier": "Reliable supplier",
        "decision.place_order_reliable_supplier.desc": "Order from the most reliable supplier.",
        "decision.place_order_cheap_supplier": "Cheap supplier",
        "decision.place_order_cheap_supplier.desc": "Order from the cheapest available supplier.",
        "decision.diversify_supplier": "Diversify suppliers",
        "decision.diversify_supplier.desc": "Order from the least-used supplier to spread risk.",
        "vocab.used_in": "Used in tools: {tools}",
        "vocab.unused": "Not attached to any tool yet",
        "vocab.needs_code": (
            "⚠ This decision is not a WRITE tool_id for this role — "
            "attach it to an organ or pick an existing tool."
        ),
        "vocab.wait_note": (
            "⚠ “Do nothing / keep watching” is always available implicitly — "
            "it needs no tool."
        ),
        "vocab.id": "Internal id",
        "vocab.display": "Name",
        "vocab.description": "Description",
        "vocab.empty": (
            "No decisions yet. Add what this employee can choose — "
            "for example “urgent reorder” or “diversify suppliers”."
        ),
        "vocab.go": "Go to action vocabulary",
        "affect.what": "What happened?",
        "affect.new_event": "+ New event",
        "affect.valence": "How bad or good is this?",
        "affect.valence_bad": "Very bad",
        "affect.valence_good": "Very good",
        "affect.arousal": "How calm or alarming is this?",
        "affect.arousal_calm": "Calm",
        "affect.arousal_alarm": "Alarming",
        "affect.presets": "Presets",
        "affect.preset.crisis": "Crisis",
        "affect.preset.success": "Success",
        "affect.preset.trust_break": "Trust break",
        "affect.preset.routine": "Routine",
        "affect.tags": "Tags",
        "affect.advanced": "Advanced (individual AffectiveSpace axes)",
        "affect.delete_event": "Delete event",
        "affect.delete_confirm": "Delete this event from the role?",
        "affect.save_preset": "Save as preset",
        "affect.preset_catalog": "Preset catalog…",
        "affect.preset_builtin": "shipped",
        "affect.preset_overlay": "overridden",
        "affect.preset_custom": "yours",
        "affect.preset_hide": "Hide",
        "affect.preset_unhide": "Show on strip",
        "affect.preset_restore": "Reset to shipped",
        "affect.preset_delete": "Delete",
        "affect.preset_id": "Preset id (latin snake_case)",
        "affect.preset_label_en": "Label (English)",
        "affect.preset_label_ru": "Label (Russian)",
        "affect.preset_overlay_warn": "This id is a shipped preset. Saving will override it for every role until you reset it.",
        "affect.intensity": "Impulse strength",
        "affect.reset_axis": "Reset",
        "affect.preview": "If only this happens (preview)",
        "affect.preview_hint": "Labels describe the state. They do not command the employee.",
        "affect.preview_neutral": "neutral / no label",
        "affect.outcome_title": "Action outcome (platform, not editable)",
        "affect.outcome_help": "WRITE status uses AffectiveSpace.outcome_impulse, not this mapping.",
        "affect.arousal_full": "arousal (−1…1)",
        "affect.arousal_negative_hint": "Full arousal is below zero — see Advanced.",
        "affect.apply": "Apply to event",
        "affect.axis.dominance": "dominance",
        "affect.axis.stress": "stress",
        "affect.axis.trust": "trust",
        "affect.axis.curiosity": "curiosity",
        "affect.axis.stability": "stability",
        "affect.axis.attachment": "attachment",
        "affect.bias.risk": "risk",
        "affect.bias.response_speed": "response speed",
        "affect.bias.word_choice": "word choice",
        "affect.bias.empathy": "empathy",
        "affect.bias.goal_priority": "goal priority",
        "affect.rank.caution": "caution",
        "affect.rank.cost_aversion": "cost aversion",
        "affect.rank.speed_seek": "speed seek",
        "affect.rank.reliability": "reliability",
        "affect.rank.novelty_seek": "novelty seek",
        "affect.rank.assertiveness": "assertiveness",
        "seed.readonly": (
            "This intuition corpus is defined in code (seed_corpus.py), "
            "not in this config. To edit it here, migrate it to inline format."
        ),
        "seed.migrate": "Move into config →",
        "seed.add": "+ Teach a decision",
        "seed.edit": "Edit lesson",
        "seed.delete": "Delete lesson",
        "seed.technical": "Show technical view",
        "seed.narrative": "Narrative view",
        "seed.empty": "No lessons yet.",
        "seed.story": (
            "When {situation} — the right decision is {decision}, "
            "because this leads to {outcome}. "
            "Importance: {importance}. Remember firmly: {reinforce}."
        ),
        "seed.unnamed": "the situation is not named",
        "seed.unspecified_outcome": "an unspecified outcome",
        "seed.yes": "yes",
        "seed.no": "no",
        "seed.importance.critical": "critical",
        "seed.importance.high": "high",
        "seed.importance.moderate": "moderate",
        "seed.importance.low": "low",
        "event.stock_critical_low": "stock is critically low",
        "event.supplier_defaulted": "a supplier defaulted",
        "event.order_arrived_on_time": "an order arrived on time",
        "event.quiet_day": "a quiet day",
        "event.demand_shock": "a demand shock",
        "event.order_arrived_late": "an order arrived late",
        "event.deal_closed_favorable": "a deal closed on favorable terms",
        "event.budget_exceeded": "the budget was exceeded",
        "event.stock_ok": "stock is above the reorder point",
        "event.stock_low_covered": "stock is low, but an order is already inbound",
        "outcome.stock_restored": "stock restored",
        "outcome.budget_preserved": "budget preserved",
        "outcome.risk_reduced": "risk reduced",
        "outcome.reliable_delivery": "reliable delivery",
        "outcome.no_action_needed": "no action needed",
        "outcome.demand_met": "demand met",
        "outcome.budget_protected": "budget protected",
        "outcome.supplier_risk_reduced": "supplier risk reduced",
        "outcome.order_already_inbound": "the order is already on its way",
        "outcome.escalated_to_finance": "escalated to finance",
        "token.budget.high_utilization": "the budget is nearly exhausted",
        "token.budget.critical": "the budget is critical",
        "decision.wait_and_monitor": "do nothing, keep watching",
        "lesson.title": "New lesson",
        "lesson.step": "Step {step} of 4",
        "lesson.when": "When this happens…",
        "lesson.then": "…the right decision is",
        "lesson.because": "…because",
        "lesson.result": "Outcome",
        "lesson.new_result": "+ new outcome",
        "lesson.how_important": "How important is this lesson?",
        "lesson.minor": "Minor",
        "lesson.critical": "Critically important",
        "lesson.reinforce": "This is a critical lesson — remember it especially firmly",
        "lesson.preview": "Preview",
        "lesson.save": "Save lesson",
        "lesson.cancel": "Cancel",
        "lesson.next": "Next →",
        "lesson.back": "← Back",
        "val.errors": "Problems that must be fixed:",
        "val.warnings": "Warnings (do not block save):",
        "val.ok": "Checked: {tools} tools, {decisions} decisions, {lessons} lessons",
        "val.save": "Save",
        "val.save_dirty": "Save *",
        "val.save_blocked": "Save (blocked until errors are fixed)",
        "val.technical": "Show technical detail",
        "val.hide_technical": "Hide technical detail",
        "val.go_lesson": "Go to lesson",
        "val.go_vocab": "Go to action vocabulary",
        "val.go_tools": "Go to tools",
        "val.teach": "Teach this decision",
        "val.history": "Change history",
        "issue.orphan_seed": (
            "A lesson refers to decision “{actions}”, which no tool declares. "
            "This lesson will never fire."
        ),
        "issue.unseeded_action": (
            "Decision “{actions}” has no lesson — the employee starts with "
            "no experience for it."
        ),
        "issue.unconfirmed_risk": (
            "Tool {tool_id}: heuristic risk {heuristic} is not confirmed yet."
        ),
        "issue.needs_motor_adapter": (
            "Decision “{action_type}” is not a WRITE tool_id for this role."
        ),
        "issue.raw": "{text}",
        "issue.invalid_risk": "A tool has an invalid risk class.",
        "issue.seed_missing_action": "A lesson has no decision label.",
        "issue.seed_source_conflict": "Choose either inline lessons or a Python module, not both.",
        "issue.malformed_list": "A list field in the config is malformed.",
        "save.title": "Save changes?",
        "save.confirm": "Save",
        "save.cancel": "Cancel",
        "save.none": "(no textual diff — structure unchanged)",
        "save.ok": "Saved to {path}",
        "save.leave_title": "Unsaved changes",
        "save.leave_body": (
            "Edits (including MCP servers, login and URL) are only in memory "
            "until you save.\n\nSave the role to disk before leaving?"
        ),
        "history.title": "Change history",
        "history.restore": "Restore this version",
        "history.diff": "Show diff",
        "history.empty": "No backups yet. They appear after the first save.",
        "downgrade.title": "Risk level lowered",
        "downgrade.body": (
            "The heuristic classed this tool as {heuristic}. "
            "You are lowering it to {requested}.\n\nWhy is this safe? (required)"
        ),
        "downgrade.confirm": "Confirm",
        "downgrade.cancel": "Cancel",
        "dryrun.scenario": "Scenario",
        "dryrun.run": "▶ Run 20 ticks",
        "dryrun.log": "Show full log",
        "dryrun.memory": "Show memory contents",
        "dryrun.memory.empty": "Memory is empty — no lessons were stored during this run.",
        "dryrun.memory.count": "{n} lessons in memory",
        "dryrun.memory.times": "This same lesson was stored {n} times.",
        "dryrun.memory.decision": "Decision: {value}",
        "dryrun.memory.situation": "Situation: {value}",
        "dryrun.memory.happened.success": "What happened: the action succeeded",
        "dryrun.memory.happened.failure": "What happened: the action failed",
        "dryrun.memory.happened.unknown": "What happened: {value}",
        "dryrun.memory.outcome": "Outcome: {value}",
        "dryrun.memory.outcome.approved": "approved",
        "dryrun.memory.outcome.rejected": "rejected",
        "dryrun.memory.importance.critical": "How important: very important — remember this firmly",
        "dryrun.memory.importance.high": "How important: important",
        "dryrun.memory.importance.moderate": "How important: moderately important",
        "dryrun.memory.importance.low": "How important: a minor lesson",
        "dryrun.close": "Close",
        "dryrun.tick": "Tick {tick}: {decision}",
        "dryrun.summary": "Over 20 ticks: {orders} orders, {rejected} rejected, {lessons} lessons stored",
        "scenario.quiet": "Quiet warehouse",
        "scenario.stock_critical": "Critical stock shortage",
        "scenario.supplier_defaulted": "Supplier defaulted",
        "statusbar.ready": "Select a role or create a new one.",
        "statusbar.ok": "✓ {tools} tools, {decisions} decisions, {lessons} lessons",
        "statusbar.dirty": "Unsaved changes",
        "statusbar.warn": "⚠ {n} warnings — save is allowed",
        "statusbar.err": "✗ {n} errors — save is blocked",
        "error.title": "Error",
        "error.params_object": "Parameters must be a JSON object",
        "prompt.tag": "Tag",
        "prompt.event": "Event name",
        "prompt.consequence": "Outcome name",
        "risk.read_only": "Read only",
        "risk.low_write": "Low write",
        "risk.medium_write": "Medium write",
        "risk.high_write": "High write",
        "risk.irreversible": "Irreversible",
        "domain.procurement": "procurement",
        "domain.finance": "finance",
        "domain.urgency": "urgency",
        "domain.risk": "risk",
        "domain.success": "success",
        "domain.trust": "trust",
        "domain.neutral": "neutral",
        "exec.accepted": "accepted",
        "exec.success": "succeeded",
        "exec.ok": "ok",
        "exec.rejected": "rejected",
        "exec.failed": "failed",
        "exec.error": "error",
        "help.button": "Help",
        "help.close": "Close",
        "help.list.title": "Help: company roles",
        "help.list.body": (
            "This is the starting screen of the Role Configurator.\n"
            "\n"
            "A role is a job description: which systems may be called, which decisions exist, "
            "how events feel, and which lessons are already known. A role cannot be started.\n"
            "\n"
            "Named employees live in the column on the right. An employee is a mind that was "
            "given one or more roles. Start and Stop never edit a role file.\n"
            "\n"
            "How to start\n"
            "1. Click a role in the list, then Open role (or double-click the line).\n"
            "2. To add a new role, click + New role and type a clear name, "
            "for example “Procurement manager”.\n"
            "3. To run a mind, click + New employee on the right, pick at least one valid role, "
            "then Open and Start.\n"
            "4. Switch the interface language with the EN / RU buttons in the top-right corner.\n"
            "\n"
            "What the marks mean\n"
            "• Valid — the configuration is in order. You can work and save.\n"
            "• Warnings — saving is still allowed. Open the Validation & preview tab to read them.\n"
            "• Invalid — there are errors. Saving is blocked until you fix them.\n"
            "\n"
            "Where the role lives\n"
            "Each role is a folder under nowa_roles/ with a config.yaml file. Until you press "
            "Save in the editor header (top right), edits exist only in memory. If you return "
            "to this list or close the window, the program will ask whether to save.\n"
            "\n"
            "Typical order for a new role\n"
            "A new role opens a short wizard (six steps). After you finish it, every tab unlocks. "
            "The usual path is: MCP servers → Tools → Action vocabulary → Affective mapping → "
            "Seed corpus → Validation & preview → Dry run.\n"
            "\n"
            "On every screen a Help button opens a page like this one."
        ),
        "help.servers.title": "Help: MCP servers",
        "help.servers.body": (
            "What this tab is for\n"
            "The employee talks to business systems (for example 1C) through MCP servers. "
            "A tool always belongs to a server, so add the server here before you pick tools "
            "on the next tab.\n"
            "\n"
            "How to add a server\n"
            "1. Click + Add MCP server.\n"
            "2. Give a short id in Latin letters (for example drive_mcp) and a display name "
            "people will recognise.\n"
            "3. Choose a transport:\n"
            "   • http or sse — fill the publication URL (it often ends with /hs/mcp/). "
            "If the publication requires a login, fill Username and Password. An empty "
            "password is allowed.\n"
            "   • mock — a training server with no network.\n"
            "   • stdio — not implemented yet.\n"
            "4. Leave Enabled on if this employee should use the server.\n"
            "\n"
            "What to do next\n"
            "Open the Tools tab and click Discover tools. After a successful poll, the server "
            "card shows two numbers: how many tools the server published, and how many of them "
            "are included in the role. If the catalog is not loaded yet, the card tells you to "
            "run Discover tools.\n"
            "\n"
            "How not to lose work\n"
            "Save is always in the editor header on the right. While the button reads Save * , "
            "changes are not on disk yet. Leaving for the role list or closing the window will "
            "ask you to save, discard, or stay.\n"
            "\n"
            "Removing a server also removes all of its tools from the role. That cannot be undone "
            "except by not saving, or by restoring a version from Change history after the first save."
        ),
        "help.tools.title": "Help: tools",
        "help.tools.body": (
            "What this tab is for\n"
            "A tool is one concrete action in a system (read stock, create a purchase order). "
            "Here you decide which tools the employee may use and how dangerous they are.\n"
            "\n"
            "Step by step\n"
            "1. Choose a server in the list at the top left. If the list is empty, go back to "
            "MCP servers first.\n"
            "2. Click Discover tools. Confirm the prompt. The configurator then asks the live "
            "server (URL and, if needed, username and password come from the previous tab).\n"
            "3. The list fills with tools from that server. Tick Include in role for the ones "
            "this employee should actually use. The others stay in the catalog but do not go "
            "into the working set.\n"
            "4. For each included tool, check Risk and Requires approval. For High write and "
            "Irreversible, human approval cannot be turned off — that is an architectural limit, "
            "not a preference.\n"
            "4b. Tick Poll as sensor only on read-only tools that the host should call by itself. "
            "Write tools cannot be polled. The default is off: the host never starts hitting a "
            "system just because a schema is empty. If a sensor has required fields, fill poll "
            "defaults on the same card or the host will skip that read and write a warning.\n"
            "5. Add decisions when you need them (the + add decision button). A decision is "
            "what the employee chooses; the tool is how that choice is carried out.\n"
            "\n"
            "Tags\n"
            "A tag is a short label for what area of work this tool belongs to. It is not a "
            "decision and not a risk level. It answers “what is this tool about?”: procurement, "
            "finance, urgency, risk, and so on.\n"
            "\n"
            "Why tags matter\n"
            "The employee sees the world as situations plus tools. The same tags tie them "
            "together. A “get stock levels” tool tagged procurement and the event “stock is "
            "critically low” with the same tags belong to one area. Without tags the tool is "
            "in the role, but nothing says which area it serves.\n"
            "\n"
            "How to add a tag\n"
            "On an included tool card click + tag. A tool may have several. Use the same words "
            "you will put on events on the Affective mapping tab:\n"
            "• procurement — stock, suppliers, purchase orders\n"
            "• finance — budget\n"
            "• urgency — time-critical work\n"
            "• risk — threat or loss\n"
            "• success — a good outcome\n"
            "• trust — reliability of a partner\n"
            "\n"
            "After Discover tools against a live server, tags are often empty — set them "
            "yourself. The mock training catalog usually already brings procurement or finance.\n"
            "\n"
            "If discovery is not available\n"
            "+ Add tool manually is a fallback when you already know the tool_id. For a live "
            "1C publication, Discover tools is the normal path.\n"
            "\n"
            "Confirming a lower risk\n"
            "If you lower the risk below the heuristic suggestion, the program asks why that is "
            "safe. Write a short reason — it is stored with the role.\n"
            "\n"
            "Remember to save\n"
            "Including a tool in the draft does not write the file until you press Save in the header."
        ),
        "help.vocab.title": "Help: action vocabulary",
        "help.vocab.body": (
            "What this tab is for\n"
            "A decision is the employee’s choice in plain language (“urgent reorder”, "
            "“reliable supplier”), not the technical tool_id. Lessons on the Seed corpus tab "
            "are written in these names.\n"
            "\n"
            "What is already there\n"
            "Every write tool in the role automatically gets a matching decision. Read-only "
            "tools do not create decisions: the employee is not “choosing” when they only look.\n"
            "\n"
            "Always available, no tool needed\n"
            "“Do nothing, keep watching” is always available by itself. You do not add it and "
            "you do not attach it to an MCP tool.\n"
            "\n"
            "How to add a decision\n"
            "Click + Add decision. Either pick a write organ that is not yet in the list, or "
            "describe a new name. A new name must match a write tool_id of this role, otherwise "
            "Validation & preview will report an error.\n"
            "\n"
            "Used in tools\n"
            "That line shows which tools mention this decision. If it says the decision is not "
            "attached yet, open Tools and add it under Decisions on the matching organ.\n"
            "\n"
            "A decision without a lesson is allowed, but the employee starts with no experience "
            "for it. The Validation & preview tab will warn you."
        ),
        "help.affect.title": "Help: affective mapping",
        "help.affect.body": (
            "What this tab is for\n"
            "Here you describe how the employee “feels” about events in the world: how bad or "
            "good they are (valence) and how calm or alarming they are (arousal). Lessons later "
            "use these events as the “when this happens” part of intuition.\n"
            "\n"
            "How to set an event\n"
            "1. Choose an event in “What happened?” or click + New event and type a clear name.\n"
            "2. Move How bad or good is this? from Very bad to Very good.\n"
            "3. Move How calm or alarming is this? from Calm to Alarming.\n"
            "4. Or click a preset — Crisis, Success, Trust break, Routine, or any you saved. "
            "The sliders jump to that template; you can still fine-tune them. Presets are "
            "shared by every role: set them once, use them everywhere.\n"
            "5. Advanced opens the remaining AffectiveSpace axes and impulse strength. "
            "The preview shows how a single step would shift decision_bias and rank_weights.\n"
            "6. Add tags if you want to mark the domain (for example procurement) or urgency. "
            "Tags are not axes.\n"
            "7. Save as preset writes the global catalog, not the role file. Save on the "
            "role still stores the event itself.\n"
            "\n"
            "Ready-made events\n"
            "Names such as “stock is critically low”, “a supplier defaulted”, or “an order "
            "arrived on time” are the training-company dictionary. Keep new names short so they "
            "read well inside a lesson on the next tab.\n"
            "\n"
            "Like everywhere else, slider changes sit in memory until you press Save."
        ),
        "help.seed.title": "Help: seed corpus",
        "help.seed.body": (
            "What this tab is for\n"
            "A lesson is a piece of ready-made intuition: “when X happens, the right decision "
            "is Y, because it leads to Z.” Without a lesson, the employee starts with no "
            "experience for that decision (Validation & preview will warn you).\n"
            "\n"
            "If you see the yellow notice\n"
            "The corpus is defined in code (seed_corpus.py), not in this YAML. Click "
            "Move into config → to edit lessons here. Until you migrate, the list is read-only.\n"
            "\n"
            "How to teach a decision\n"
            "1. Click + Teach a decision. A four-step wizard opens.\n"
            "2. When this happens… — pick an event from Affective mapping.\n"
            "3. …the right decision is — pick a name from Action vocabulary.\n"
            "4. …because / Outcome — say why that choice is right.\n"
            "5. Set how important the lesson is. Tick “remember it especially firmly” for "
            "critical rules.\n"
            "6. Read the preview, then Save lesson.\n"
            "\n"
            "The list shows each lesson as a short story. Show technical view reveals internal "
            "codes if you need to match names with the YAML file.\n"
            "\n"
            "A lesson that names a decision no tool declares will never fire. Fix that on "
            "Validation & preview (it is an error, not a warning)."
        ),
        "help.validation.title": "Help: validation and preview",
        "help.validation.body": (
            "What this tab is for\n"
            "Before the role goes to work, the configurator checks the draft in memory "
            "(even if the file on disk is still the old version).\n"
            "\n"
            "Problems that must be fixed\n"
            "These block Save, both in the header and on this page. Typical causes: an invalid "
            "risk class, a lesson that names an unknown decision, or a decision that is not a "
            "write tool of this role.\n"
            "\n"
            "Warnings (do not block save)\n"
            "You may still save. Examples: a decision with no lesson (the employee starts with "
            "no experience), or a heuristic risk that you have not confirmed yet.\n"
            "\n"
            "How to jump to the fix\n"
            "Go to tools, Go to action vocabulary, and Go to lesson open the matching tab. "
            "Show technical detail switches to the internal wording for debugging.\n"
            "\n"
            "Saving\n"
            "Save is in the editor header on every tab, and again on this page. After the first "
            "successful save, Change history keeps backups — you can show a diff or restore a "
            "previous version.\n"
            "\n"
            "The status bar at the bottom repeats the same idea: unsaved changes, warnings "
            "allowed, or errors blocking save."
        ),
        "help.dryrun.title": "Help: dry run",
        "help.dryrun.body": (
            "What this tab is for\n"
            "A short lab run: 20 ticks with the current draft. You see which decisions the "
            "employee takes and what is stored in memory. This does not talk to live 1C and "
            "does not write the role file.\n"
            "\n"
            "When it will run\n"
            "The draft must have no blocking errors (the same rule as Save). You do not have "
            "to press Save first: the run copies the in-memory draft to a temporary file.\n"
            "\n"
            "How to run it\n"
            "1. Choose a scenario: Quiet warehouse, Critical stock shortage, or Supplier defaulted.\n"
            "2. Click ▶ Run 20 ticks.\n"
            "3. The summary counts orders, rejected actions, and lessons stored. The journal "
            "lists the decision on each tick.\n"
            "\n"
            "Show full log and Show memory contents open longer views in plain language "
            "(not raw JSON). Memory contents groups repeated lessons so you can see what "
            "stuck.\n"
            "\n"
            "If the run is silent or memory stays empty, go back to Action vocabulary and "
            "Seed corpus: there may be no matching decision, or a lesson may point at the "
            "wrong event.\n"
            "\n"
            "Pending write actions in the lab are auto-approved so you can watch the loop. "
            "That is only for this test, not a change to Requires approval on the Tools tab.\n"
            "\n"
            "This lab run is not an employee. A named mind with live MCP is started from "
            "the Employees column on the home screen, not from this tab."
        ),
        "help.employees.title": "Help: employees",
        "help.employees.body": (
            "This column is the employee host, next to company roles.\n"
            "\n"
            "A role describes the work: servers, organs, risk, seed, affect. An employee is a "
            "named mind that was given one or more roles. Start and Stop never edit a role YAML file.\n"
            "\n"
            "How to start\n"
            "1. Create an employee with a unique id, at least one valid role, a tick interval, "
            "and a sleep interval.\n"
            "2. Open the employee card. Start is available when the employee is stopped or in "
            "error and the composed roles are valid.\n"
            "3. Approve write actions only on this card. The list may show a pending count; "
            "that is an invitation to open the card, not a second decision channel.\n"
            "Unchecking Requires approval in the role editor does nothing until you Save the "
            "role and Restart the employee. The tick log records the chosen action, not a "
            "successful MCP write; a write reaches Drive only after Approve (or when that "
            "tool has approval turned off and the session was started after the save).\n"
            "\n"
            "Not sent: business limits\n"
            "A role can declare business limits, such as a budget. A write that does not fit "
            "never reaches the approval queue or Drive. The card shows it in orange, once per "
            "shortage (not on every tick), with the reason and the amount left; the list shows "
            "a count. This is for a person to act on, e.g. allocate budget. Alerts are kept "
            "across Stop and Start. Clear hides the seen alerts; it changes nothing in the "
            "mind or in Drive.\n"
            "\n"
            "Tick versus sleep\n"
            "Tick is how often the employee looks at the world. Sleep is how often experience "
            "is consolidated. Sleeping on every tick will break learning.\n"
            "\n"
            "Memory\n"
            "Stop writes a full mind checkpoint. The next Start restores that mind and does "
            "not reseed intuition unless memory is empty. Closing this window with live "
            "employees asks whether to stop them and save memory.\n"
            "\n"
            "The Dry run tab of a role is a lab check of the YAML. It does not start this "
            "employee and does not talk to a live publication.\n"
            "\n"
            "Delete on the employee card or list stops a live session if needed, then removes "
            "the employee folder (yaml, mind, sidecar). That is not the same as Reset memory."
        ),
    },
    "ru": {
        "app.title": "NOWA Role Configurator",
        "cli.description": "Конфигуратор ролей NOWA",
        "cli.lang_help": "Язык интерфейса. Важнее NOWA_LANG и сохранённого выбора.",
        "lang.en": "EN",
        "lang.ru": "RU",
        "list.heading": "Роли компании",
        "list.empty": "В nowa_roles/ ролей не найдено",
        "list.meta": "{domain} · {tools} тулов · {lessons} уроков · изменено {when}",
        "list.new": "+ Новая роль",
        "list.open": "Открыть роль",
        "list.back": "← К ролям",
        "emp.heading": "Сотрудники",
        "emp.empty": "Сотрудников пока нет. Создайте, чтобы запустить разум.",
        "emp.new": "+ Новый сотрудник",
        "emp.open": "Открыть",
        "emp.delete": "Удалить",
        "emp.start": "Старт",
        "emp.stop": "Стоп",
        "emp.restart": "Рестарт",
        "emp.back": "← Сотрудники",
        "emp.roles_line": "роли: {roles}",
        "emp.rhythm_line": "тик {tick}с · сон ≥ {sleep}",
        "emp.pending": "pending: {n}",
        "emp.status.stopped": "остановлен",
        "emp.status.starting": "запускается",
        "emp.status.running": "работает",
        "emp.status.sleeping": "спит",
        "emp.status.awaiting_approval": "ждёт одобрения",
        "emp.status.stopping": "останавливается",
        "emp.status.error": "ошибка",
        "emp.new.title": "Новый сотрудник",
        "emp.new.name": "Имя",
        "emp.new.id": "id",
        "emp.new.roles": "Роли (хотя бы одна, только ✓-валидные):",
        "emp.new.rhythm": "Ритм",
        "emp.new.tick": "Тик (секунд)",
        "emp.new.sleep": "Сон не чаще чем раз в (секунд)",
        "emp.new.create": "Создать",
        "emp.new.cancel": "Отмена",
        "emp.roles": "Роли",
        "emp.add_role": "+ добавить роль",
        "emp.tick": "Тик",
        "emp.sensor": "Опрос сенсоров",
        "emp.sleep_min": "Сон не чаще чем раз в",
        "emp.sleep_window": "Окно сна (часы)",
        "emp.fatigue": "Порог усталости",
        "emp.seconds": "с",
        "emp.mcp": "MCP",
        "emp.organs": "Органы: {read} READ / {write} WRITE · last sensor {when}",
        "emp.memory": "Память: checkpoint {when} · {n} эпизодов",
        "emp.stale": "Роли изменены после старта — рестартните сотрудника, чтобы подхватить новый YAML.",
        "emp.approval": "Очередь одобрения",
        "emp.alerts": "Не отправлено: бизнес-лимиты ({n})",
        "emp.alerts_clear": "Очистить",
        "emp.alerts_badge": "⚠ не отправлено: {n}",
        "emp.alert_line": "{at}  {limit}: {summary} — {reason}",
        "emp.alert_reason.nothing_left": "денег не осталось",
        "emp.alert_reason.over_available": "не хватает даже на единицу (осталось {available})",
        "emp.approve": "Одобрить",
        "emp.reject": "Отклонить",
        "emp.edit_params": "Править params",
        "emp.write_failed": "Запись не создала документ.\n{status}: {detail}",
        "emp.write_ok": "Документ создан: {number}",
        "emp.qty_zero_confirm": "qty = 0 — Drive скорее всего отклонит заказ. Одобрить всё равно?",
        "emp.log": "Журнал тиков (хвост)",
        "emp.narrative": "Память (narrative)",
        "emp.reset_memory": "Сбросить память",
        "emp.reset_confirm": "Удалить чекпоинт разума и sidecar этого сотрудника? Следующий Старт посеет интуицию, если она включена.",
        "emp.delete_confirm": "Удалить сотрудника «{name}» и его память? Если он запущен, сначала будет Стоп. Это нельзя отменить.",
        "emp.close_running": "Остановить {n} сотрудников и сохранить память?",
        "emp.close_title": "Работающие сотрудники",
        "emp.sleep_zero_confirm": "Интервал сна 0 позволит спать на каждом тике и сломает обучение. Продолжить?",
        "emp.sleep_hint": "Тик — как часто сотрудник смотрит на мир. Сон — как часто он закрепляет опыт. Сон раз в тик сломает обучение.",
        "emp.none": "—",
        "emp.ago": "{n}с назад",
        "status.valid": "валиден",
        "status.warnings": "{n} предупреждения",
        "status.error": "ошибка",
        "new.title": "Новая роль",
        "new.display_name": "Отображаемое имя",
        "new.create": "Создать",
        "new.cancel": "Отмена",
        "tab.servers": "MCP-серверы",
        "tab.tools": "Инструменты",
        "tab.vocab": "Словарь решений",
        "tab.affect": "Эмоциональные реакции",
        "tab.seed": "Профессиональная интуиция",
        "tab.validation": "Проверка",
        "tab.dryrun": "Тестовый прогон",
        "wizard.banner": "Мастер новой роли — шаг {step} из 6. После этого вкладки разблокируются.",
        "wizard.next": "Далее →",
        "wizard.back": "← Назад",
        "wizard.finish": "Завершить мастер",
        "servers.intro": (
            "Каждый сотрудник подключается к одному или нескольким MCP-серверам. "
            "Инструменты принадлежат серверу и хранятся вложенно."
        ),
        "servers.add": "+ Добавить MCP-сервер",
        "servers.empty": (
            "Пока нет ни одного MCP-сервера. Добавьте сервер здесь — "
            "затем его тулы на следующей вкладке."
        ),
        "servers.id": "Идентификатор (например 1c_erp)",
        "servers.display": "Отображаемое имя",
        "servers.transport": "Транспорт",
        "servers.enabled": "Включён",
        "servers.command": "Команда (stdio)",
        "servers.args": "Аргументы",
        "servers.url": "URL (sse / http)",
        "servers.username": "Логин",
        "servers.password": "Пароль",
        "servers.tools_count": "На сервере: {catalog} · в роли: {included}",
        "servers.tools_count_no_catalog": (
            "В роли: {included} · каталог не загружен — нажмите «Обнаружить тулы»"
        ),
        "servers.remove": "Удалить сервер",
        "servers.remove_confirm": (
            "Удалить сервер «{server}» и все его тулы из этой роли?"
        ),
        "servers.title": "Новый MCP-сервер",
        "servers.placeholder": (
            "Для http / sse укажите URL и, если публикация этого требует, "
            "логин и пароль (пустой пароль допустим). "
            "Затем на вкладке инструментов нажмите «Обнаружить тулы». "
            "stdio появится позже."
        ),
        "tools.discover": "Обнаружить тулы",
        "tools.discover_done": "Найдено тулов: {n} (уже в роли: {included}).",
        "tools.add_manual": "+ Добавить тул вручную",
        "tools.server": "Сервер",
        "tools.risk": "Риск",
        "tools.approval": "Требуется одобрение",
        "tools.approval_auto_off": "авто, выкл.",
        "tools.approval_locked": "Требуется (нельзя выключить)",
        "tools.heuristic": "предложено эвристикой",
        "tools.confirm_risk": "Подтвердить риск",
        "tools.decisions": "Решения",
        "tools.add_decision": "+ добавить решение",
        "tools.tags": "Теги",
        "tools.add_tag": "+ тег",
        "tools.not_included": "Не включена в роль — тул с необратимым риском",
        "tools.high_note": (
            "* HIGH_WRITE/IRREVERSIBLE не могут работать без одобрения человека — "
            "это архитектурное ограничение (assert_stage2_invariant), не настройка."
        ),
        "tools.included": "Включить в роль",
        "tools.poll": "Опрашивать как сенсор",
        "tools.poll_defaults": "Значения опроса (обязательные поля)",
        "tools.poll_write": "WRITE нельзя опрашивать",
        "tools.no_server": "Сначала добавьте MCP-сервер на предыдущей вкладке.",
        "tools.go_servers": "Перейти к MCP-серверам",
        "manual.title": "Добавить тул вручную",
        "manual.tool_id": "tool_id",
        "manual.display": "Отображаемое имя",
        "manual.description": "Описание",
        "manual.server": "Сервер",
        "vocab.intro": "Какие решения может принимать этот сотрудник?",
        "vocab.add": "+ Добавить решение",
        "vocab.add_title": "Новое решение",
        "vocab.name_label": "Как называется это решение?",
        "vocab.name_hint": "Короткое имя, которое поймёт сотрудник, например «Срочный дозаказ».",
        "vocab.desc_label": "Что сотрудник делает, когда выбирает его?",
        "vocab.desc_hint": "Одно-два предложения своими словами. Технический код создаётся автоматически.",
        "vocab.add_confirm": "Добавить",
        "vocab.source_label": "Откуда взять решение?",
        "vocab.from_adapter": "Выбрать WRITE-орган, уже зарегистрированный в роли",
        "vocab.from_custom": "Описать новое решение (оно должно совпадать с WRITE tool_id)",
        "vocab.adapter_pick": "Доступные WRITE-органы",
        "vocab.adapter_empty": "Все WRITE-органы уже есть в списке.",
        "decision.mcp__1c__create_purchase_order": "Создать заказ поставщику",
        "decision.mcp__1c__create_purchase_order.desc": "Оформить заказ по текущим остаткам и поставщикам.",
        "decision.mcp__drivemcp__create_purchase_order": "Создать заказ поставщику",
        "decision.mcp__drivemcp__create_purchase_order.desc": "Оформить заказ по текущим остаткам и поставщикам.",
        "decision.urgent_reorder": "Срочный дозаказ",
        "decision.urgent_reorder.desc": "Заказать у самого быстрого поставщика, не глядя на цену.",
        "decision.place_order_reliable_supplier": "Надёжный поставщик",
        "decision.place_order_reliable_supplier.desc": "Заказать у самого надёжного поставщика.",
        "decision.place_order_cheap_supplier": "Дешёвый поставщик",
        "decision.place_order_cheap_supplier.desc": "Заказать у самого дешёвого поставщика.",
        "decision.diversify_supplier": "Диверсификация поставщиков",
        "decision.diversify_supplier.desc": "Заказать у наименее используемого поставщика.",
        "vocab.used_in": "Используется в инструментах: {tools}",
        "vocab.unused": "Пока не привязано ни к одному инструменту",
        "vocab.needs_code": (
            "⚠ Это решение не является WRITE tool_id этой роли — "
            "привяжите его к органу или выберите существующий тул."
        ),
        "vocab.wait_note": (
            "⚠ Решение «ничего не делать, просто наблюдать» всегда доступно "
            "само — без инструмента."
        ),
        "vocab.id": "Внутренний id",
        "vocab.display": "Название",
        "vocab.description": "Описание",
        "vocab.empty": (
            "Пока нет ни одного решения. Добавьте, что сотрудник умеет выбирать — "
            "например «срочный дозаказ» или «диверсификация поставщиков»."
        ),
        "vocab.go": "Перейти к словарю решений",
        "affect.what": "Что происходит?",
        "affect.new_event": "+ Новое событие",
        "affect.valence": "Насколько это плохо или хорошо?",
        "affect.valence_bad": "Очень плохо",
        "affect.valence_good": "Очень хорошо",
        "affect.arousal": "Насколько это тревожно или спокойно?",
        "affect.arousal_calm": "Спокойно",
        "affect.arousal_alarm": "Тревожно",
        "affect.presets": "Пресеты",
        "affect.preset.crisis": "Кризис",
        "affect.preset.success": "Успех",
        "affect.preset.trust_break": "Разрыв доверия",
        "affect.preset.routine": "Рутина",
        "affect.tags": "Теги",
        "affect.advanced": "Продвинутая настройка (отдельные оси AffectiveSpace)",
        "affect.delete_event": "Удалить событие",
        "affect.delete_confirm": "Удалить это событие из роли?",
        "affect.save_preset": "Сохранить как пресет",
        "affect.preset_catalog": "Справочник…",
        "affect.preset_builtin": "заводской",
        "affect.preset_overlay": "оверлей",
        "affect.preset_custom": "свой",
        "affect.preset_hide": "Скрыть",
        "affect.preset_unhide": "Вернуть на полосу",
        "affect.preset_restore": "Сбросить к поставке",
        "affect.preset_delete": "Удалить",
        "affect.preset_id": "Id пресета (латиница snake_case)",
        "affect.preset_label_en": "Подпись (EN)",
        "affect.preset_label_ru": "Подпись (RU)",
        "affect.preset_overlay_warn": "Этот id — заводской пресет. Сохранение переопределит его для всех ролей, пока не сбросите.",
        "affect.intensity": "Сила импульса",
        "affect.reset_axis": "Сбросить",
        "affect.preview": "Если случится только это (превью)",
        "affect.preview_hint": "Ярлыки описывают состояние, сотрудник по ним не ветвится.",
        "affect.preview_neutral": "нейтрально / нет ярлыка",
        "affect.outcome_title": "Исход действия (платформа, не редактируется)",
        "affect.outcome_help": "WRITE-статус идёт через AffectiveSpace.outcome_impulse, не через этот маппинг.",
        "affect.arousal_full": "arousal (−1…1)",
        "affect.arousal_negative_hint": "Задан полный arousal ниже нуля — смотрите продвинутую настройку.",
        "affect.apply": "Применить к событию",
        "affect.axis.dominance": "dominance",
        "affect.axis.stress": "stress",
        "affect.axis.trust": "trust",
        "affect.axis.curiosity": "curiosity",
        "affect.axis.stability": "stability",
        "affect.axis.attachment": "attachment",
        "affect.bias.risk": "риск",
        "affect.bias.response_speed": "скорость ответа",
        "affect.bias.word_choice": "выбор слов",
        "affect.bias.empathy": "эмпатия",
        "affect.bias.goal_priority": "приоритет цели",
        "affect.rank.caution": "осторожность",
        "affect.rank.cost_aversion": "избегание цены",
        "affect.rank.speed_seek": "скорость",
        "affect.rank.reliability": "надёжность",
        "affect.rank.novelty_seek": "новизна",
        "affect.rank.assertiveness": "напористость",
        "seed.readonly": (
            "Этот словарь интуиции определён в коде (seed_corpus.py), "
            "не в этом конфиге. Чтобы редактировать через интерфейс, "
            "сначала перенесите его в inline-формат."
        ),
        "seed.migrate": "Перенести в конфиг →",
        "seed.add": "+ Научить решению",
        "seed.edit": "Редактировать урок",
        "seed.delete": "Удалить урок",
        "seed.technical": "Показать технический вид",
        "seed.narrative": "Повествовательный вид",
        "seed.empty": "Уроков пока нет.",
        "seed.story": (
            "Когда {situation} — правильное решение «{decision}», "
            "потому что это ведёт к «{outcome}». "
            "Важность: {importance}. Запомнить крепко: {reinforce}."
        ),
        "seed.unnamed": "ситуация не названа",
        "seed.unspecified_outcome": "результат не указан",
        "seed.yes": "да",
        "seed.no": "нет",
        "seed.importance.critical": "критическая",
        "seed.importance.high": "высокая",
        "seed.importance.moderate": "средняя",
        "seed.importance.low": "низкая",
        "event.stock_critical_low": "запас критически низкий",
        "event.supplier_defaulted": "поставщик подвёл",
        "event.order_arrived_on_time": "заказ пришёл вовремя",
        "event.quiet_day": "спокойный день",
        "event.demand_shock": "скачок спроса",
        "event.order_arrived_late": "заказ пришёл с опозданием",
        "event.deal_closed_favorable": "сделка закрыта на выгодных условиях",
        "event.budget_exceeded": "бюджет превышен",
        "event.stock_ok": "запас выше точки заказа",
        "event.stock_low_covered": "запас низкий, но заказ уже в пути",
        "outcome.stock_restored": "запас восстановлен",
        "outcome.budget_preserved": "бюджет сохранён",
        "outcome.risk_reduced": "риск снижен",
        "outcome.reliable_delivery": "надёжная поставка",
        "outcome.no_action_needed": "ничего делать не нужно",
        "outcome.demand_met": "спрос закрыт",
        "outcome.budget_protected": "бюджет защищён",
        "outcome.supplier_risk_reduced": "риск по поставщику снижен",
        "outcome.order_already_inbound": "заказ уже в пути",
        "outcome.escalated_to_finance": "передано финансам",
        "token.budget.high_utilization": "бюджет почти исчерпан",
        "token.budget.critical": "бюджет на пределе",
        "decision.wait_and_monitor": "ничего не делать, наблюдать",
        "lesson.title": "Новый урок",
        "lesson.step": "Шаг {step} из 4",
        "lesson.when": "Когда это происходит…",
        "lesson.then": "…правильное решение —",
        "lesson.because": "…потому что —",
        "lesson.result": "Результат",
        "lesson.new_result": "+ новый результат",
        "lesson.how_important": "Насколько важен этот урок?",
        "lesson.minor": "Незначительный",
        "lesson.critical": "Критически важный",
        "lesson.reinforce": "Это критически важный урок — запомнить особенно крепко",
        "lesson.preview": "Предпросмотр",
        "lesson.save": "Сохранить урок",
        "lesson.cancel": "Отмена",
        "lesson.next": "Далее →",
        "lesson.back": "← Назад",
        "val.errors": "Найдены проблемы, требующие исправления:",
        "val.warnings": "Предупреждения (не блокируют сохранение):",
        "val.ok": "Проверено: {tools} инструментов, {decisions} решений, {lessons} уроков",
        "val.save": "Сохранить",
        "val.save_dirty": "Сохранить *",
        "val.save_blocked": "Сохранить (заблокировано, пока есть ошибки)",
        "val.technical": "Показать техническую деталь",
        "val.hide_technical": "Скрыть техническую деталь",
        "val.go_lesson": "Перейти к уроку",
        "val.go_vocab": "Перейти к словарю решений",
        "val.go_tools": "Перейти к инструментам",
        "val.teach": "Научить решению",
        "val.history": "История изменений",
        "issue.orphan_seed": (
            "Урок ссылается на решение «{actions}», которого нет ни в одном "
            "инструменте. Этот урок никогда не сработает."
        ),
        "issue.unseeded_action": (
            "Решение «{actions}» не имеет ни одного урока — сотрудник начнёт "
            "без опыта по этому решению."
        ),
        "issue.unconfirmed_risk": (
            "Тул {tool_id}: риск {heuristic} предложен эвристикой и ещё не подтверждён."
        ),
        "issue.needs_motor_adapter": (
            "Решение «{action_type}» не является WRITE tool_id этой роли."
        ),
        "issue.raw": "{text}",
        "issue.invalid_risk": "У инструмента указан недопустимый класс риска.",
        "issue.seed_missing_action": "У урока нет метки решения.",
        "issue.seed_source_conflict": "Укажите либо inline-уроки, либо Python-модуль, не оба сразу.",
        "issue.malformed_list": "Одно из списковых полей конфига задано неверно.",
        "save.title": "Сохранить изменения?",
        "save.confirm": "Сохранить",
        "save.cancel": "Отмена",
        "save.none": "(текстового diff нет — структура не изменилась)",
        "save.ok": "Сохранено в {path}",
        "save.leave_title": "Есть несохранённые изменения",
        "save.leave_body": (
            "Правки (включая MCP-серверы, логин и URL) живут только в памяти, "
            "пока вы не сохраните роль.\n\nСохранить роль на диск перед выходом?"
        ),
        "history.title": "История изменений",
        "history.restore": "Откатить к этой версии",
        "history.diff": "Показать diff",
        "history.empty": "Бэкапов пока нет. Они появятся после первого сохранения.",
        "downgrade.title": "Понижение уровня риска",
        "downgrade.body": (
            "Эвристика определила этот тул как {heuristic}. "
            "Вы понижаете до {requested}.\n\nПочему это безопасно? (обязательно)"
        ),
        "downgrade.confirm": "Подтвердить",
        "downgrade.cancel": "Отмена",
        "dryrun.scenario": "Сценарий",
        "dryrun.run": "▶ Прогнать 20 тактов",
        "dryrun.log": "Показать полный лог",
        "dryrun.memory": "Показать содержимое памяти",
        "dryrun.memory.empty": "Память пуста — за этот прогон уроков не накопилось.",
        "dryrun.memory.count": "Уроков в памяти: {n}",
        "dryrun.memory.times": "Этот же урок записан {n} раз.",
        "dryrun.memory.decision": "Решение: {value}",
        "dryrun.memory.situation": "Ситуация: {value}",
        "dryrun.memory.happened.success": "Что произошло: действие завершилось успешно",
        "dryrun.memory.happened.failure": "Что произошло: действие не удалось",
        "dryrun.memory.happened.unknown": "Что произошло: {value}",
        "dryrun.memory.outcome": "Итог: {value}",
        "dryrun.memory.outcome.approved": "одобрено",
        "dryrun.memory.outcome.rejected": "отклонено",
        "dryrun.memory.importance.critical": "Насколько важно: очень важно — запомнить крепко",
        "dryrun.memory.importance.high": "Насколько важно: важно",
        "dryrun.memory.importance.moderate": "Насколько важно: умеренно важно",
        "dryrun.memory.importance.low": "Насколько важно: незначительный урок",
        "dryrun.close": "Закрыть",
        "dryrun.tick": "Такт {tick}: {decision}",
        "dryrun.summary": "За 20 тактов: {orders} заказов, {rejected} отклонено, накоплено {lessons} уроков",
        "scenario.quiet": "Склад спокоен",
        "scenario.stock_critical": "Критический дефицит на складе",
        "scenario.supplier_defaulted": "Поставщик подвёл",
        "statusbar.ready": "Выберите роль или создайте новую.",
        "statusbar.ok": "✓ {tools} инструментов, {decisions} решений, {lessons} уроков",
        "statusbar.dirty": "Есть несохранённые изменения",
        "statusbar.warn": "⚠ {n} предупреждений — сохранение разрешено",
        "statusbar.err": "✗ {n} ошибок — сохранение заблокировано",
        "error.title": "Ошибка",
        "error.params_object": "Параметры должны быть JSON-объектом",
        "prompt.tag": "Тег",
        "prompt.event": "Имя события",
        "prompt.consequence": "Имя результата",
        "risk.read_only": "Только чтение",
        "risk.low_write": "Небольшая запись",
        "risk.medium_write": "Средняя запись",
        "risk.high_write": "Опасная запись",
        "risk.irreversible": "Необратимо",
        "domain.procurement": "закупки",
        "domain.finance": "финансы",
        "domain.urgency": "срочность",
        "domain.risk": "риск",
        "domain.success": "успех",
        "domain.trust": "доверие",
        "domain.neutral": "нейтрально",
        "exec.accepted": "принято",
        "exec.success": "успешно",
        "exec.ok": "ок",
        "exec.rejected": "отклонено",
        "exec.failed": "не удалось",
        "exec.error": "ошибка",
        "help.button": "Справка",
        "help.close": "Закрыть",
        "help.list.title": "Справка: роли компании",
        "help.list.body": (
            "Это стартовый экран конфигуратора ролей.\n"
            "\n"
            "Роль — описание работы: к каким системам можно обращаться, какие решения "
            "умеет принимать сотрудник, как он реагирует на события и какие уроки уже есть. "
            "Роль нельзя запустить.\n"
            "\n"
            "Именованные сотрудники — колонка справа. Сотрудник — разум, которому эту "
            "работу выдали. Старт и Стоп не правят файл роли.\n"
            "\n"
            "Как начать\n"
            "1. Выберите роль в списке и нажмите «Открыть роль» (или дважды щёлкните строку).\n"
            "2. Чтобы завести новую роль, нажмите «+ Новая роль» и введите понятное "
            "имя, например «Менеджер по закупкам».\n"
            "3. Чтобы запустить разум, справа нажмите «+ Новый сотрудник», отметьте хотя бы "
            "одну валидную роль, затем «Открыть» и «Старт».\n"
            "4. Язык интерфейса переключается кнопками EN / RU в правом верхнем углу.\n"
            "\n"
            "Что значат пометки у роли\n"
            "• Валиден — конфиг в порядке, можно работать и сохранять.\n"
            "• Предупреждения — сохранять можно. Откройте вкладку «Проверка», чтобы прочитать их.\n"
            "• Ошибка — есть проблемы. Сохранение заблокировано, пока их не исправить.\n"
            "\n"
            "Где хранится роль\n"
            "Каждая роль — папка в nowa_roles/ с файлом config.yaml. Пока вы не нажмёте "
            "«Сохранить» в шапке редактора (справа вверху), правки живут только в памяти. "
            "Если вернуться к этому списку или закрыть окно, программа спросит, сохранить ли черновик.\n"
            "\n"
            "Обычный порядок для новой роли\n"
            "Новая роль открывает короткий мастер (шесть шагов). Когда вы его завершите, "
            "все вкладки разблокируются. Дальше обычно так: MCP-серверы → Инструменты → "
            "Словарь решений → Эмоциональные реакции → Профессиональная интуиция → "
            "Проверка → Тестовый прогон.\n"
            "\n"
            "На каждом экране кнопка «Справка» открывает такую же инструкцию по этой странице."
        ),
        "help.servers.title": "Справка: MCP-серверы",
        "help.servers.body": (
            "Зачем эта вкладка\n"
            "Сотрудник обращается к учётным системам (например 1С) через MCP-серверы. "
            "Тул всегда принадлежит серверу, поэтому сначала добавьте сервер здесь, "
            "а инструменты выбирайте на следующей вкладке.\n"
            "\n"
            "Как добавить сервер\n"
            "1. Нажмите «+ Добавить MCP-сервер».\n"
            "2. Задайте короткий идентификатор латиницей (например drive_mcp) и отображаемое имя, "
            "по которому сервер узнают люди.\n"
            "3. Выберите транспорт:\n"
            "   • http или sse — укажите URL публикации (часто заканчивается на /hs/mcp/). "
            "Если публикация требует вход, заполните «Логин» и «Пароль». Пустой пароль допустим.\n"
            "   • mock — учебный сервер без сети.\n"
            "   • stdio — пока не реализован.\n"
            "4. Оставьте галочку «Включён», если этот сотрудник должен пользоваться сервером.\n"
            "\n"
            "Что делать дальше\n"
            "Откройте вкладку «Инструменты» и нажмите «Обнаружить тулы». После успешного опроса "
            "на карточке сервера появятся два числа: сколько тулов опубликовал сервер и сколько "
            "из них включено в роль. Если каталог ещё не загружен, карточка напомнит нажать "
            "«Обнаружить тулы».\n"
            "\n"
            "Как не потерять работу\n"
            "Кнопка «Сохранить» всегда в шапке редактора справа. Пока на ней «Сохранить *», "
            "изменения не записаны на диск. Уход к списку ролей или закрытие окна спросит: "
            "сохранить, отбросить или остаться.\n"
            "\n"
            "Удаление сервера снимает с роли и все его тулы. Это нельзя отменить, кроме как "
            "не сохранять черновик или восстановить версию из «Истории изменений» после первого сохранения."
        ),
        "help.tools.title": "Справка: инструменты",
        "help.tools.body": (
            "Зачем эта вкладка\n"
            "Тул — конкретное действие в системе (посмотреть остатки, создать заказ поставщику). "
            "Здесь вы решаете, какими тулами сотрудник пользуется и насколько они опасны.\n"
            "\n"
            "Пошагово\n"
            "1. Выберите сервер в списке слева вверху. Если список пуст, сначала вернитесь "
            "на вкладку «MCP-серверы».\n"
            "2. Нажмите «Обнаружить тулы» и подтвердите запрос. Конфигуратор опросит живой "
            "сервер (URL и, если нужно, логин с паролем берутся с предыдущей вкладки).\n"
            "3. В списке появятся тулы с сервера. Отметьте «Включить в роль» те, которыми "
            "сотрудник реально должен пользоваться. Остальные остаются в каталоге, но в работу "
            "не попадают.\n"
            "4. Для каждого включённого тула проверьте «Риск» и «Требуется одобрение». "
            "Для «Опасная запись» и «Необратимо» одобрение человеком нельзя выключить — "
            "это ограничение архитектуры, не настройка.\n"
            "4б. Галочка «Опрашивать как сенсор» ставится только на чтение: хост сам "
            "дергает эти тулы по интервалу сотрудника. WRITE опрашивать нельзя. По умолчанию "
            "выкл.: хост не начинает бить в систему только потому, что схема пустая. "
            "Если у датчика есть обязательные поля — заполните значения опроса на той же "
            "карточке, иначе этот цикл тул будет пропущен с предупреждением в журнале.\n"
            "5. При необходимости добавьте решения (кнопка «+ добавить решение»). "
            "Решение — то, что сотрудник выбирает; тул — чем он это исполняет.\n"
            "\n"
            "Теги\n"
            "Тег — короткая метка области, к которой относится тул. Это не решение и не риск, "
            "а ответ на вопрос «про что этот инструмент»: закупки, финансы, срочность, риск.\n"
            "\n"
            "Зачем они нужны\n"
            "Сотрудник видит мир как ситуации плюс инструменты. Одинаковые теги связывают их. "
            "Тул «посмотреть остатки» с тегом закупки и событие «запас критически низкий» "
            "с теми же тегами относятся к одной области. Без тегов тул есть в роли, но нигде "
            "не сказано, какой сфере он служит.\n"
            "\n"
            "Как поставить\n"
            "На карточке включённого тула нажмите «+ тег». Тегов может быть несколько. "
            "Вводите те же английские слова, что и у событий на вкладке «Эмоциональные реакции» — "
            "в карточке они отобразятся по-русски:\n"
            "• procurement — закупки (остатки, поставщики, заказ)\n"
            "• finance — финансы (бюджет)\n"
            "• urgency — срочность\n"
            "• risk — риск\n"
            "• success — успех\n"
            "• trust — доверие\n"
            "\n"
            "После «Обнаружить тулы» с живого сервера тегов часто нет — проставьте их сами. "
            "Учебный mock обычно уже приносит procurement или finance.\n"
            "\n"
            "Если опрос недоступен\n"
            "«+ Добавить тул вручную» — запасной путь, когда вы уже знаете tool_id. "
            "Для живой публикации 1С обычно достаточно «Обнаружить тулы».\n"
            "\n"
            "Понижение риска\n"
            "Если вы ставите риск ниже, чем предложила эвристика, программа спросит, почему "
            "это безопасно. Коротко напишите причину — она сохранится вместе с ролью.\n"
            "\n"
            "Не забудьте сохранить\n"
            "Галочка «Включить в роль» не пишет файл, пока вы не нажмёте «Сохранить» в шапке."
        ),
        "help.vocab.title": "Справка: словарь решений",
        "help.vocab.body": (
            "Зачем эта вкладка\n"
            "Решение — выбор сотрудника своими словами («срочный дозаказ», «надёжный поставщик»), "
            "а не технический tool_id. Уроки на вкладке «Профессиональная интуиция» пишутся "
            "именно этими именами.\n"
            "\n"
            "Что уже есть\n"
            "Для каждого WRITE-тула в роли автоматически появляется одноимённое решение. "
            "Тулам «только чтение» решения не создаются: сотрудник ничего не «выбирает», "
            "когда только смотрит данные.\n"
            "\n"
            "Всегда доступно без тула\n"
            "Решение «ничего не делать, наблюдать» есть всегда само по себе. Его не нужно "
            "добавлять и не нужно привязывать к MCP-инструменту.\n"
            "\n"
            "Как добавить решение\n"
            "Нажмите «+ Добавить решение». Либо выберите WRITE-орган, которого ещё нет в списке, "
            "либо опишите новое имя. Новое имя должно совпасть с WRITE tool_id этой роли, "
            "иначе вкладка «Проверка» покажет ошибку.\n"
            "\n"
            "Используется в инструментах\n"
            "Эта строка показывает, какие тулы ссылаются на решение. Если написано, что оно "
            "пока ни к чему не привязано, откройте «Инструменты» и добавьте его в поле "
            "«Решения» нужного органа.\n"
            "\n"
            "Решение без урока сохранить можно, но сотрудник начнёт без опыта по нему. "
            "Вкладка «Проверка» предупредит об этом."
        ),
        "help.affect.title": "Справка: эмоциональные реакции",
        "help.affect.body": (
            "Зачем эта вкладка\n"
            "Здесь вы описываете, как сотрудник «чувствует» события мира: насколько они "
            "плохие или хорошие и насколько спокойные или тревожные. Позже уроки интуиции "
            "берут эти события как часть «когда это происходит».\n"
            "\n"
            "Как настроить событие\n"
            "1. Выберите событие в списке «Что происходит?» или нажмите «+ Новое событие» "
            "и введите понятное имя.\n"
            "2. Двиньте ползунок «Насколько это плохо или хорошо?» от «Очень плохо» "
            "до «Очень хорошо».\n"
            "3. Двиньте ползунок «Насколько это тревожно или спокойно?» от «Спокойно» "
            "до «Тревожно».\n"
            "4. Либо нажмите пресет — «Кризис», «Успех», «Разрыв доверия», «Рутина» или свой. "
            "Ползунки встанут по шаблону, их можно подправить. Справочник общий для всех ролей: "
            "задали один раз — пользуетесь везде.\n"
            "5. «Продвинутая настройка» открывает остальные оси AffectiveSpace и силу импульса. "
            "Превью показывает, как один шаг сдвинет decision_bias и rank_weights.\n"
            "6. При необходимости добавьте теги (например область «закупки» или срочность). "
            "Теги не являются осями.\n"
            "7. «Сохранить как пресет» пишет общий справочник, не файл роли. «Сохранить» роли "
            "по-прежнему записывает само событие.\n"
            "\n"
            "Готовые события\n"
            "Имена вроде «запас критически низкий», «поставщик подвёл», «заказ пришёл вовремя» — "
            "словарь учебной компании. Новые имена держите короткими, чтобы они читались "
            "внутри урока на следующей вкладке.\n"
            "\n"
            "Как и везде, сдвиг ползунков попадает в файл только после «Сохранить»."
        ),
        "help.seed.title": "Справка: профессиональная интуиция",
        "help.seed.body": (
            "Зачем эта вкладка\n"
            "Урок — заготовка интуиции: «когда случилось X, правильное решение — Y, потому что "
            "это ведёт к Z». Без урока сотрудник стартует без опыта по этому решению "
            "(вкладка «Проверка» покажет предупреждение).\n"
            "\n"
            "Если видите жёлтую плашку\n"
            "Словарь интуиции задан в коде (seed_corpus.py), а не в этом YAML. Нажмите "
            "«Перенести в конфиг →», чтобы редактировать уроки здесь. Пока не перенесёте, "
            "список только для чтения.\n"
            "\n"
            "Как научить решению\n"
            "1. Нажмите «+ Научить решению». Откроется мастер из четырёх шагов.\n"
            "2. «Когда это происходит…» — выберите событие со вкладки «Эмоциональные реакции».\n"
            "3. «…правильное решение —» — выберите имя из «Словаря решений».\n"
            "4. «…потому что» и «Результат» — зачем так поступать.\n"
            "5. Укажите важность урока. Галочка «запомнить особенно крепко» усиливает "
            "критические правила.\n"
            "6. Прочитайте предпросмотр и нажмите «Сохранить урок».\n"
            "\n"
            "В списке урок читается короткой фразой. «Показать технический вид» раскрывает "
            "внутренние коды, если нужно сверить имена с YAML.\n"
            "\n"
            "Урок, который ссылается на решение, которого нет ни в одном инструменте, "
            "никогда не сработает. Это ошибка на вкладке «Проверка», а не предупреждение."
        ),
        "help.validation.title": "Справка: проверка",
        "help.validation.body": (
            "Зачем эта вкладка\n"
            "Перед тем как отдать роль в работу, конфигуратор проверяет черновик в памяти "
            "(даже если файл на диске ещё старый).\n"
            "\n"
            "Проблемы, требующие исправления\n"
            "Пока они есть, «Сохранить» заблокирован и в шапке, и на этой странице. "
            "Типичные причины: недопустимый класс риска, урок на неизвестное решение, "
            "решение, которое не является WRITE-тулом этой роли.\n"
            "\n"
            "Предупреждения (не блокируют сохранение)\n"
            "Сохранять можно. Например: решение без урока (сотрудник начнёт без опыта) "
            "или риск, который эвристика предложила, а вы ещё не подтвердили.\n"
            "\n"
            "Как перейти к исправлению\n"
            "Кнопки «Перейти к инструментам», «Перейти к словарю решений» и «Перейти к уроку» "
            "открывают нужную вкладку. «Показать техническую деталь» включает внутренние "
            "формулировки для отладки.\n"
            "\n"
            "Сохранение\n"
            "«Сохранить» есть в шапке редактора на любой вкладке и ещё раз на этой странице. "
            "После первого успешного сохранения в «Истории изменений» появляются бэкапы — "
            "можно показать diff или откатиться.\n"
            "\n"
            "Строка состояния внизу окна повторяет то же самое: есть несохранённые изменения, "
            "предупреждения не мешают сохранить, ошибки блокируют сохранение."
        ),
        "help.dryrun.title": "Справка: тестовый прогон",
        "help.dryrun.body": (
            "Зачем эта вкладка\n"
            "Короткий лабораторный прогон: 20 тактов по текущему черновику. Так видно, "
            "какие решения принимает сотрудник и что оседает в памяти. Это не обращение "
            "к живой 1С и не запись файла роли.\n"
            "\n"
            "Когда прогон запустится\n"
            "В черновике не должно быть блокирующих ошибок (то же правило, что у «Сохранить»). "
            "Сначала жать «Сохранить» не обязательно: прогон копирует черновик из памяти "
            "во временный файл.\n"
            "\n"
            "Как запустить\n"
            "1. Выберите сценарий: «Склад спокоен», «Критический дефицит на складе» "
            "или «Поставщик подвёл».\n"
            "2. Нажмите «▶ Прогнать 20 тактов».\n"
            "3. Сводка покажет число заказов, отказов и накопленных уроков. В журнале — "
            "решение на каждом такте.\n"
            "\n"
            "«Показать полный лог» и «Показать содержимое памяти» открывают подробности "
            "простым языком (не сырой JSON). Одинаковые уроки в памяти группируются, "
            "чтобы было видно, что запомнилось.\n"
            "\n"
            "Если прогон «молчит» или память пуста, вернитесь к «Словарю решений» и "
            "«Профессиональной интуиции»: возможно, нет подходящего решения или урок "
            "ссылается не на то событие.\n"
            "\n"
            "Записи, которые в лаборатории ждут одобрения, здесь подтверждаются автоматически, "
            "чтобы цикл было видно. Это только для теста, а не изменение галочки "
            "«Требуется одобрение» на вкладке «Инструменты».\n"
            "\n"
            "Это не сотрудник. Именованный разум с живыми MCP запускается из колонки "
            "«Сотрудники» на главном экране, не с этой вкладки."
        ),
        "help.employees.title": "Справка: сотрудники",
        "help.employees.body": (
            "Это колонка хоста сотрудников, рядом со списком ролей.\n"
            "\n"
            "Роль описывает работу: серверы, органы, риск, seed, аффект. Сотрудник — "
            "именованный разум, которому эту работу выдали. Старт и Стоп не правят YAML роли.\n"
            "\n"
            "Как начать\n"
            "1. Создайте сотрудника с уникальным id, хотя бы одной валидной ролью, интервалом "
            "тика и интервалом сна.\n"
            "2. Откройте карточку. Старт доступен, когда сотрудник остановлен или в ошибке "
            "и состав ролей проходит проверку.\n"
            "3. WRITE одобряют только в карточке. Счётчик pending в списке — приглашение "
            "открыть карточку, не второй канал решения.\n"
            "Снятие «нужно одобрение» в редакторе роли не действует, пока роль не сохранена "
            "и сотрудник не перезапущен. Журнал тиков пишет выбранное действие, а не "
            "успешную запись в MCP: в Drive вызов уходит только после «Одобрить» (или если "
            "у тула снято одобрение и сессия стартовала уже после сохранения).\n"
            "\n"
            "Не отправлено: бизнес-лимиты\n"
            "Роль может объявить бизнес-лимиты, например бюджет. WRITE, который в них не "
            "укладывается, не попадает ни в очередь одобрения, ни в Drive. Карточка показывает "
            "его оранжевым один раз на эпизод нехватки (не на каждом тике), с причиной и "
            "остатком; в списке виден счётчик. Это сигнал человеку, например выделить бюджет. "
            "Предупреждения сохраняются между Стоп и Старт. «Очистить» убирает просмотренные предупреждения и ничего не меняет ни в разуме, "
            "ни в Drive.\n"
            "\n"
            "Тик и сон\n"
            "Тик — как часто сотрудник смотрит на мир. Сон — как часто он закрепляет опыт. "
            "Сон раз в тик сломает обучение.\n"
            "\n"
            "Память\n"
            "Стоп пишет полный чекпоинт разума. Следующий Старт поднимает того же и не "
            "пересеивает интуицию, пока память не пуста. Закрытие окна с живыми сотрудниками "
            "спрашивает, остановить ли их и сохранить память.\n"
            "\n"
            "Вкладка «Тестовый прогон» роли — лабораторная проверка YAML. Она не стартует "
            "этого сотрудника и не ходит в живую публикацию.\n"
            "\n"
            "«Удалить» на карточке или в списке останавливает живую сессию при необходимости "
            "и снимает папку сотрудника (yaml, разум, sidecar). Это не то же самое, что "
            "«Сбросить память»."
        ),
    },
}

HELP_TOPICS = (
    "list",
    "employees",
    "servers",
    "tools",
    "vocab",
    "affect",
    "seed",
    "validation",
    "dryrun",
)


def assert_string_parity() -> None:
    en = set(STRINGS["en"])
    ru = set(STRINGS["ru"])
    if en != ru:
        raise AssertionError(
            f"i18n key mismatch; missing in ru={sorted(en - ru)}, "
            f"missing in en={sorted(ru - en)}"
        )


class I18n:
    """Key → string translator with optional preference file."""

    def __init__(
        self,
        lang: str = DEFAULT_LANG,
        pref_path: Optional[Path] = None,
        *,
        force: bool = False,
    ) -> None:
        """Resolve language: ``force`` (``--lang``) > ``NOWA_LANG`` > saved pref > argument."""

        self.pref_path = pref_path
        if lang not in SUPPORTED:
            lang = DEFAULT_LANG
        if not force:
            env = os.environ.get("NOWA_LANG", "").strip().lower()
            if env in SUPPORTED:
                lang = env
            elif pref_path and pref_path.exists():
                try:
                    data = json.loads(pref_path.read_text(encoding="utf-8"))
                    saved = data.get("lang")
                    if saved in SUPPORTED:
                        lang = saved
                except (OSError, json.JSONDecodeError, TypeError):
                    pass
        self._lang = lang

    @property
    def lang(self) -> str:
        return self._lang

    def set_language(self, lang: str) -> None:
        if lang not in SUPPORTED:
            raise ValueError(f"Unsupported language: {lang}")
        self._lang = lang
        if self.pref_path is not None:
            try:
                self.pref_path.parent.mkdir(parents=True, exist_ok=True)
                self.pref_path.write_text(
                    json.dumps({"lang": lang}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except OSError:
                pass

    def t(self, key: str, **kwargs: Any) -> str:
        table = STRINGS.get(self._lang) or STRINGS[DEFAULT_LANG]
        text = table.get(key) or STRINGS[DEFAULT_LANG].get(key) or key
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, ValueError):
                return text
        return text

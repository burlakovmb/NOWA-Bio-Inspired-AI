"""Phase-1 host name for the platform GenericEncoder.

Live runtime calls ``encode(world_state)``. ``encode_tool_result`` /
``encode_action_outcome`` keep the older host contract.
Token buckets and outcome vectors come from ``mcp_body.generic_encoder``;
``token_rules.generic_tokens: false`` drops its generic buckets.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ._compat import ensure_core_src_on_path, impulse_to_vector

ensure_core_src_on_path()

from affective_space import mapped_event_tokens  # noqa: E402
from mcp_body.generic_encoder import GenericEncoder  # noqa: E402
from mcp_body.mcp_client import tool_name_from_tool_id  # noqa: E402


class BusinessEventEncoder(GenericEncoder):
    """GenericEncoder plus Phase-1 token helpers and ``token_rules.generic_tokens``."""

    def generic_tokens_enabled(self) -> bool:
        """``token_rules.generic_tokens: false`` keeps only mapped business events.

        Generic ``tool:/status:/field:/entity:`` tokens let a role work without
        an event classifier, but once a classifier names the events they only
        dilute recall: a lesson written as ``event:*`` tokens then matches the
        live context at a fraction of its real similarity. Impulses are kept.
        """
        return bool(self.token_rules.get("generic_tokens", True))

    def _tokens_for_tool(self, tool_id: str, payload: Dict[str, Any]) -> List[str]:
        if not self.generic_tokens_enabled():
            return []
        return super()._tokens_for_tool(tool_id, payload)

    def _field_bucket_tokens(self, world_state: Any) -> List[str]:
        if not self.generic_tokens_enabled():
            return []
        return super()._field_bucket_tokens(world_state)

    def _entity_tokens(self, world_state: Any) -> List[str]:
        if not self.generic_tokens_enabled():
            return []
        return super()._entity_tokens(world_state)

    def encode_tool_result(
        self,
        tool_id: str,
        result: Any,
        event_classifier: Any = None,
        world_state: Any = None,
    ) -> List[str]:
        payload = result if isinstance(result, dict) else {"value": result}
        events: List[str] = []
        if callable(event_classifier):
            try:
                events = [str(item) for item in (event_classifier(str(tool_id), payload) or [])]
            except Exception:
                events = []
        if events:
            tokens: List[str] = []
            for event in events:
                entry = self.affective_mapping.get(event)
                if isinstance(entry, dict):
                    tokens.extend(mapped_event_tokens(event, entry))
                else:
                    tokens.append(f"event:{event}")
            return tokens or [f"event:{tool_name_from_tool_id(tool_id) or tool_id}"]

        name = tool_name_from_tool_id(tool_id) or str(tool_id).rsplit("__", 1)[-1]
        return [f"event:{name}"]

    def encode_action_outcome(
        self,
        _intent: str,
        result: Any,
    ) -> Tuple[List[str], Dict[str, float]]:
        envelope = result if isinstance(result, dict) else {"status": result}
        tokens, impulse = self.encode_outcome(
            str(envelope.get("status", "unknown")),
            envelope,
            tool_id="",
        )
        status_key = str(envelope.get("status", "") or "unknown").strip().lower()
        if status_key not in ("accepted", "success", "ok", "rejected", "failed", "error"):
            return ["result:unknown"], {}
        return tokens[:1], impulse_to_vector(impulse)


BusinessEventImpulse = dict

__all__ = ["BusinessEventEncoder", "BusinessEventImpulse", "GenericEncoder"]

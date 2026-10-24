"""Strict ``param_bindings``: a value comes only from the path the role names.

```yaml
param_bindings:
  slot_id: {path: entities.items.0.id, strict: true}
```

The platform ``SchemaBinder`` falls back to guessing (exact name, ranked
enum, recalled values) when an explicit binding finds nothing. For a strict
binding an empty path means the world said there is nothing to act on;
guessing elsewhere would turn that into a call on the wrong entity. The
binder then returns ``None`` and names the first required parameter that
missed in ``last_strict_miss``. Non-strict bindings keep the fallback.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._compat import ensure_core_src_on_path

ensure_core_src_on_path()

from mcp_body.schema_binder import SchemaBinder  # noqa: E402


class StrictSchemaBinder(SchemaBinder):
    """``SchemaBinder`` that honours ``strict: true`` in a role's bindings."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.last_strict_miss: Optional[str] = None

    def bind(self, *args: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        self.last_strict_miss = None
        return super().bind(*args, **kwargs)

    def _bind_property(self, name: str, prop: Dict[str, Any], world_state: Any, weights: Dict[str, float],
                       hippocampus: Any, param_bindings: Dict[str, Any], aliases: Optional[Dict[str, Any]],
                       tool_id: str, bound: Dict[str, Any], required: bool) -> Any:
        if is_strict_binding(name, param_bindings) and (
            self._explicit_binding(name, param_bindings, world_state) is None
        ):
            if required and self.last_strict_miss is None:
                self.last_strict_miss = name
            return None
        return super()._bind_property(
            name=name,
            prop=prop,
            world_state=world_state,
            weights=weights,
            hippocampus=hippocampus,
            param_bindings=param_bindings,
            aliases=aliases,
            tool_id=tool_id,
            bound=bound,
            required=required,
        )


def is_strict_binding(name: str, param_bindings: Optional[Dict[str, Any]]) -> bool:
    spec = (param_bindings or {}).get(name)
    return isinstance(spec, dict) and bool(spec.get("strict", False))


__all__ = ["StrictSchemaBinder", "is_strict_binding"]

"""Safe agent-state documents.

The file is UTF-8 JSON. It names a format and a schema version, then a tree of
plain values and a closed set of core types. Nothing in the file is imported
or called. Old pickle bytes are rejected before they are parsed.
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, FrozenSet, Iterable, Tuple, Type


AGENT_STATE_FORMAT = "nowa-agent-state"
AGENT_STATE_SCHEMA_VERSION = 1

_TAG = "__nowa_type__"
_REGISTRY: Dict[Type[Any], str] = {}
_BY_NAME: Dict[str, Type[Any]] = {}
_READY = False


class StateFormatError(ValueError):
    """The file is not a supported state document."""


def dump_state(path: Any, state: Any, *, format_id: str, schema_version: int) -> None:
    """Atomically write one versioned document. The previous file stays intact on failure."""
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise StateFormatError(f"schema version must be an integer, got {schema_version!r}")
    document = {
        "format": str(format_id),
        "schema_version": int(schema_version),
        "state": encode_tree(state),
    }
    try:
        text = json.dumps(document, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise StateFormatError(f"state is not JSON-safe: {exc}") from exc
    target = os.fspath(path)
    parent = os.path.dirname(target) or "."
    os.makedirs(parent, exist_ok=True)
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(
            prefix=f".{os.path.basename(target)}.",
            suffix=".tmp",
            dir=parent,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def load_state(
    path: Any,
    *,
    expected_format: str,
    supported_versions: Iterable[int],
) -> Any:
    """Read a document or raise ``StateFormatError`` without executing file contents."""
    target = os.fspath(path)
    try:
        with open(target, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise StateFormatError(f"cannot read save file {target}: {exc}") from exc
    if _looks_like_pickle(raw):
        raise StateFormatError(
            "Old pickle saves are not supported and cannot be loaded."
        )
    try:
        parsed = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StateFormatError(
            f"Unrecognized save format; expected a JSON {expected_format} document."
        ) from exc
    if not isinstance(parsed, dict):
        raise StateFormatError(
            f"Unrecognized save format; expected a JSON {expected_format} document."
        )
    found = parsed.get("format")
    if found != expected_format:
        raise StateFormatError(
            f"Save format {found!r} is not a {expected_format} document."
        )
    version = parsed.get("schema_version")
    allowed = _version_set(supported_versions)
    if isinstance(version, bool) or not isinstance(version, int) or version not in allowed:
        supported = ", ".join(str(item) for item in sorted(allowed))
        raise StateFormatError(
            f"Unsupported schema version {version!r}; this build reads version {supported}."
        )
    if "state" not in parsed:
        raise StateFormatError("Save document has no state.")
    try:
        return decode_tree(parsed["state"])
    except StateFormatError:
        raise
    except (TypeError, ValueError) as exc:
        raise StateFormatError(f"Save state could not be restored: {exc}") from exc


def encode_tree(value: Any) -> Any:
    """Return a JSON-ready tree. Unknown objects raise ``StateFormatError``."""
    _ensure_registry()
    encoder = _Encoder()
    encoder.count(value, set())
    return encoder.encode(value)


def decode_tree(value: Any) -> Any:
    """Inverse of ``encode_tree``. Type tags outside the allow-list are rejected."""
    _ensure_registry()
    return _Decoder().decode(value)


def _version_set(versions: Iterable[int]) -> FrozenSet[int]:
    allowed = []
    for item in versions:
        if isinstance(item, bool) or not isinstance(item, int):
            raise StateFormatError(f"supported schema version must be an integer, got {item!r}")
        allowed.append(int(item))
    return frozenset(allowed)


def _looks_like_pickle(raw: bytes) -> bool:
    if not raw:
        return False
    if raw.startswith(b"\x80"):
        return True
    head = raw.lstrip()
    # Protocol 0/1: GLOBAL (`cos\\nsystem`), MARK, EMPTY_DICT, EMPTY_LIST.
    if head[:1] in (b"c", b"(", b"]", b"}"):
        return True
    return head.startswith((b"I", b"V", b"S"))


def _ensure_registry() -> None:
    global _READY
    if _READY:
        return
    from affective_space import EmotionalTrace
    from experience import Event, EventType, Experience, Path
    from hippocampus import SignatureTrace
    from sleep import CorticalPattern

    for cls in (Experience, Path, Event, EmotionalTrace, SignatureTrace, CorticalPattern):
        _register(cls)
    _register(EventType)
    _READY = True


def _register(cls: Type[Any]) -> None:
    name = cls.__name__
    _REGISTRY[cls] = name
    _BY_NAME[name] = cls


class _Encoder:
    def __init__(self) -> None:
        self.counts: Dict[int, int] = {}
        self.emitted: Dict[int, int] = {}
        self.next_id = 1

    def count(self, obj: Any, visiting: set) -> None:
        if not _is_shareable(obj):
            if isinstance(obj, tuple):
                oid = id(obj)
                if oid in visiting:
                    return
                visiting.add(oid)
                try:
                    for item in obj:
                        self.count(item, visiting)
                finally:
                    visiting.discard(oid)
            return
        oid = id(obj)
        self.counts[oid] = self.counts.get(oid, 0) + 1
        if oid in visiting or self.counts[oid] > 1:
            return
        visiting.add(oid)
        try:
            for child in _children(obj):
                self.count(child, visiting)
        finally:
            visiting.discard(oid)

    def encode(self, obj: Any) -> Any:
        leaf = _encode_leaf(obj)
        if leaf is not _MISSING:
            return leaf
        if isinstance(obj, tuple):
            return {_TAG: "tuple", "items": [self.encode(item) for item in obj]}
        if not _is_shareable(obj):
            raise StateFormatError(
                "cannot serialize "
                f"{type(obj).__module__}.{type(obj).__name__}"
            )
        oid = id(obj)
        if oid in self.emitted:
            return {_TAG: "ref", "id": self.emitted[oid]}
        shared = self.counts.get(oid, 0) > 1
        assigned = None
        if shared:
            assigned = self.next_id
            self.next_id += 1
            self.emitted[oid] = assigned
        body = self._encode_body(obj)
        if assigned is not None:
            body["id"] = assigned
        return body

    def _encode_body(self, obj: Any) -> Dict[str, Any]:
        name = _REGISTRY.get(type(obj))
        if name is not None:
            if name == "EventType":
                return {_TAG: "enum", "name": name, "value": obj.name}
            state = _object_state(obj)
            return {
                _TAG: "obj",
                "name": name,
                "state": {key: self.encode(value) for key, value in state.items()},
            }
        if isinstance(obj, list):
            return {_TAG: "list", "items": [self.encode(item) for item in obj]}
        if isinstance(obj, deque_type()):
            maxlen = obj.maxlen
            return {
                _TAG: "deque",
                "maxlen": None if maxlen is None else int(maxlen),
                "items": [self.encode(item) for item in obj],
            }
        if isinstance(obj, (set, frozenset)):
            kind = "frozenset" if isinstance(obj, frozenset) else "set"
            items = _ordered_set(obj)
            return {_TAG: kind, "items": [self.encode(item) for item in items]}
        if isinstance(obj, dict):
            if _plain_dict(obj):
                return {_TAG: "dict", "items": {str(key): self.encode(value) for key, value in obj.items()}}
            pairs = [[self.encode(key), self.encode(value)] for key, value in obj.items()]
            return {_TAG: "map", "items": pairs}
        raise StateFormatError(
            f"cannot serialize {type(obj).__module__}.{type(obj).__name__}"
        )


class _Decoder:
    def __init__(self) -> None:
        self.memo: Dict[int, Any] = {}

    def decode(self, node: Any) -> Any:
        if isinstance(node, list):
            return [self.decode(item) for item in node]
        if not isinstance(node, dict) or _TAG not in node:
            if isinstance(node, dict):
                return {str(key): self.decode(value) for key, value in node.items()}
            return node
        kind = node[_TAG]
        if kind == "ref":
            try:
                return self.memo[int(node["id"])]
            except (KeyError, TypeError, ValueError) as exc:
                raise StateFormatError(f"dangling state reference {node.get('id')!r}") from exc
        if kind == "tuple":
            return tuple(self.decode(item) for item in list(node.get("items") or []))
        if kind == "enum":
            return _decode_enum(node)
        if kind == "float":
            return _decode_float(node)
        if kind == "bytes":
            try:
                return base64.b64decode(str(node.get("b64") or ""), validate=True)
            except (ValueError, TypeError) as exc:
                raise StateFormatError("invalid bytes payload") from exc
        if kind == "datetime":
            try:
                return datetime.fromisoformat(str(node.get("value")))
            except ValueError as exc:
                raise StateFormatError("invalid datetime payload") from exc
        if kind == "date":
            try:
                return date.fromisoformat(str(node.get("value")))
            except ValueError as exc:
                raise StateFormatError("invalid date payload") from exc
        shared_id = node.get("id")
        if kind == "obj":
            return self._decode_obj(node, shared_id)
        if kind == "list":
            shell = []
            self._remember(shared_id, shell)
            for item in list(node.get("items") or []):
                shell.append(self.decode(item))
            return shell
        if kind == "dict":
            shell = {}
            self._remember(shared_id, shell)
            items = node.get("items")
            if not isinstance(items, dict):
                raise StateFormatError("dict payload must be an object")
            for key, value in items.items():
                shell[str(key)] = self.decode(value)
            return shell
        if kind == "map":
            shell = {}
            self._remember(shared_id, shell)
            for pair in list(node.get("items") or []):
                if not isinstance(pair, list) or len(pair) != 2:
                    raise StateFormatError("map entry must be a pair")
                shell[self.decode(pair[0])] = self.decode(pair[1])
            return shell
        if kind == "deque":
            from collections import deque

            maxlen = node.get("maxlen")
            shell = deque(maxlen=None if maxlen is None else int(maxlen))
            self._remember(shared_id, shell)
            for item in list(node.get("items") or []):
                shell.append(self.decode(item))
            return shell
        if kind in ("set", "frozenset"):
            values = [self.decode(item) for item in list(node.get("items") or [])]
            try:
                built = frozenset(values) if kind == "frozenset" else set(values)
            except TypeError as exc:
                raise StateFormatError("set payload contains an unhashable item") from exc
            self._remember(shared_id, built)
            return built
        raise StateFormatError(f"unknown state tag {kind!r}")

    def _remember(self, shared_id: Any, obj: Any) -> None:
        if shared_id is None:
            return
        try:
            key = int(shared_id)
        except (TypeError, ValueError) as exc:
            raise StateFormatError(f"invalid state id {shared_id!r}") from exc
        if key in self.memo:
            raise StateFormatError(f"duplicate state id {key}")
        self.memo[key] = obj

    def _decode_obj(self, node: Dict[str, Any], shared_id: Any) -> Any:
        name = node.get("name")
        cls = _BY_NAME.get(str(name))
        if cls is None or name == "EventType":
            raise StateFormatError(f"unknown stored type {name!r}")
        state = node.get("state")
        if not isinstance(state, dict):
            raise StateFormatError(f"stored {name} state must be an object")
        if name == "CorticalPattern":
            obj = cls.__new__(cls)
            self._remember(shared_id, obj)
            restored = {key: self.decode(value) for key, value in state.items()}
            for key, value in restored.items():
                setattr(obj, key, value)
            return obj
        obj = cls.__new__(cls)
        self._remember(shared_id, obj)
        restored = {key: self.decode(value) for key, value in state.items()}
        if not hasattr(obj, "__setstate__"):
            raise StateFormatError(f"stored type {name} cannot be restored")
        obj.__setstate__(restored)
        return obj


_MISSING = object()


def _encode_leaf(obj: Any) -> Any:
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, int) and not isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        if obj != obj:
            return {_TAG: "float", "value": "nan"}
        if obj == float("inf"):
            return {_TAG: "float", "value": "inf"}
        if obj == float("-inf"):
            return {_TAG: "float", "value": "-inf"}
        return obj
    if isinstance(obj, Enum):
        name = _REGISTRY.get(type(obj))
        if name is None:
            raise StateFormatError(
                f"cannot serialize enum {type(obj).__module__}.{type(obj).__name__}"
            )
        return {_TAG: "enum", "name": name, "value": obj.name}
    if isinstance(obj, (bytes, bytearray)):
        return {_TAG: "bytes", "b64": base64.b64encode(bytes(obj)).decode("ascii")}
    if isinstance(obj, datetime):
        return {_TAG: "datetime", "value": obj.isoformat()}
    if isinstance(obj, date):
        return {_TAG: "date", "value": obj.isoformat()}
    return _MISSING


def _decode_enum(node: Dict[str, Any]) -> Enum:
    name = str(node.get("name") or "")
    cls = _BY_NAME.get(name)
    if cls is None or not isinstance(cls, type) or not issubclass(cls, Enum):
        raise StateFormatError(f"unknown stored enum {name!r}")
    member = str(node.get("value") or "")
    try:
        return cls[member]
    except KeyError as exc:
        raise StateFormatError(f"unknown {name} value {member!r}") from exc


def _decode_float(node: Dict[str, Any]) -> float:
    token = str(node.get("value") or "")
    if token == "nan":
        return float("nan")
    if token == "inf":
        return float("inf")
    if token == "-inf":
        return float("-inf")
    raise StateFormatError(f"invalid float token {token!r}")


def _is_shareable(obj: Any) -> bool:
    if isinstance(obj, tuple) or obj is None:
        return False
    if isinstance(obj, (bool, int, float, str, bytes, bytearray, datetime, date, Enum)):
        return False
    if type(obj) in _REGISTRY and type(obj).__name__ != "EventType":
        return True
    if isinstance(obj, (list, dict, set, frozenset)):
        return True
    return isinstance(obj, deque_type())


def deque_type():
    from collections import deque

    return deque


def _children(obj: Any) -> Tuple[Any, ...]:
    name = _REGISTRY.get(type(obj))
    if name is not None and name != "EventType":
        return tuple(_object_state(obj).values())
    if isinstance(obj, dict):
        values = []
        for key, value in obj.items():
            values.append(key)
            values.append(value)
        return tuple(values)
    if isinstance(obj, (list, set, frozenset)) or isinstance(obj, deque_type()):
        return tuple(obj)
    return ()


def _object_state(obj: Any) -> Dict[str, Any]:
    getter = getattr(obj, "__getstate__", None)
    if callable(getter):
        state = getter()
    else:
        state = dict(vars(obj))
    if not isinstance(state, dict):
        raise StateFormatError(
            f"{type(obj).__name__} state must be a dict, got {type(state).__name__}"
        )
    return state


def _plain_dict(obj: dict) -> bool:
    for key in obj:
        if not isinstance(key, str) or key == _TAG or key.startswith("__nowa_"):
            return False
    return True


def _ordered_set(obj: Iterable[Any]) -> list:
    items = list(obj)
    try:
        return sorted(items, key=lambda item: (type(item).__name__, repr(item)))
    except TypeError:
        return items

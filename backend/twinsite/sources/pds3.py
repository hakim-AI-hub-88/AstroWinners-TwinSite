"""Minimal PDS3 ODL label parser (enough for MOLA MEGDR / LOLA GDR IMG labels)."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from .base import DecodeError

_UNIT = re.compile(r"^(.*?)\s*<([^>]+)>\s*$", re.S)


def _value(raw: str) -> Any:
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"'):
        return " ".join(raw[1:-1].split())
    m = _UNIT.match(raw)
    if m:
        return {"value": _value(m.group(1)), "unit": m.group(2).strip()}
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def parse_label(text: str) -> Dict[str, Any]:
    """Return a nested dict; OBJECT blocks become ``{"OBJECT:NAME": {...}}``
    (with ``#2`` suffixes when the same object name repeats)."""
    if "PDS_VERSION_ID" not in text:
        raise DecodeError("not a PDS3 label (PDS_VERSION_ID missing)")
    root: Dict[str, Any] = {}
    stack: List[Tuple[str, Dict[str, Any]]] = [("ROOT", root)]
    lines = text.replace("\r", "").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].split("/*")[0].rstrip()
        i += 1
        if not line.strip():
            continue
        if line.strip() == "END":
            break
        if "=" not in line:
            raise DecodeError(f"malformed label line {i}: {line[:60]!r}")
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if val.startswith('"') and (val.count('"') % 2 == 1):
            buf = [val]
            while i < len(lines):
                nxt = lines[i]
                i += 1
                buf.append(nxt)
                if nxt.count('"') % 2 == 1:
                    break
            else:
                raise DecodeError("unterminated quoted string in label")
            val = "\n".join(buf)
        if key == "OBJECT":
            name = val
            cur = stack[-1][1]
            slot = f"OBJECT:{name}"
            n = 2
            while slot in cur:
                slot = f"OBJECT:{name}#{n}"
                n += 1
            child: Dict[str, Any] = {}
            cur[slot] = child
            stack.append((name, child))
        elif key == "END_OBJECT":
            if len(stack) == 1 or stack[-1][0] != val:
                raise DecodeError(f"unbalanced END_OBJECT {val}")
            stack.pop()
        else:
            stack[-1][1][key] = _value(val)
    if len(stack) != 1:
        raise DecodeError("label ended inside an OBJECT")
    return root


def num(v: Any) -> float:
    if isinstance(v, dict):
        v = v["value"]
    return float(v)

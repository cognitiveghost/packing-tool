"""The bridge: the one object Packer Mode's order document talks to (ADR 0001).

Modelled on shopify-fulfillment-tool's gui/results_bridge.py. Every message is
its own named member, never a generic send(kind, data). State Python owns
crosses as a notify Property, so a page that connects late reads the current
value with no handshake; what JS reports crosses as a Slot. Channel members are
camelCase because JS calls them.

The payload functions below are pure -- no Qt, no I/O -- so the numbers and the
action rules are testable without a browser. They are the only place that
decides an item's state; packer.js renders what they say.

Spec: docs/superpowers/specs/2026-09-18-phase10-bundle4-web-seam-design.md
"""

from typing import Any

from packing_tool.packer_logic import normalize_sku

# Force confirm is for quantities nobody wants to scan one at a time. Below
# this it is a foot-gun with no upside, and today's UI already hides it.
FORCE_CONFIRM_MIN_QTY = 5


def _int(value: Any, default: int = 1) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def item_rows(
    items: list[dict[str, Any]],
    order_state: list[dict[str, Any]],
    sku_map: dict[str, str],
) -> list[dict[str, Any]]:
    """One row per order item, with its state and the actions it offers."""
    packed_by_row = {
        _int(s.get("row"), 0): _int(s.get("packed"), 0) for s in order_state or []
    }
    mapped = {normalize_sku(v) for v in (sku_map or {}).values()}

    rows = []
    for index, item in enumerate(items):
        sku = str(item.get("SKU", ""))
        required = max(_int(item.get("Quantity")), 1)
        packed = packed_by_row.get(index, 0)
        if packed >= required:
            state = "complete"
        elif packed > 0:
            state = "partial"
        else:
            state = "pending"
        rows.append(
            {
                "row": index,
                "product": str(item.get("Product_Name", "")),
                "sku": sku,
                "required": required,
                "packed": packed,
                "state": state,
                "just_changed": False,
                "confirm": packed < required,
                "undo": packed > 0,
                "force": required > FORCE_CONFIRM_MIN_QTY and packed < required,
                "map": normalize_sku(sku) not in mapped,
            }
        )
    return rows

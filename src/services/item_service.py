"""Item usage tracking service."""
from collections import OrderedDict
from typing import Optional
from src.database import get_db
from src.commands import ITEMS


# Quick lookup for item metadata
ITEM_INDEX = {
    item["name"]: {**item, "category": category}
    for category, items in ITEMS.items()
    for item in items
}


def record_item_usage(user_id: int, item_name, amount=1):
    """Persist item usage counts for quick-access ordering for a specific user."""
    if item_name not in ITEM_INDEX:
        return
    try:
        amount_int = max(int(amount), 1)
    except (TypeError, ValueError):
        amount_int = 1

    db = get_db()
    db.execute(
        """
        INSERT INTO item_usage (item, user_id, used_count, last_used)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(item, user_id) DO UPDATE SET
            used_count = item_usage.used_count + excluded.used_count,
            last_used = CURRENT_TIMESTAMP
        """,
        (item_name, user_id, amount_int),
    )
    db.commit()


def fetch_usage_counts(user_id: Optional[int] = None):
    """Get usage counts for all items for a specific user."""
    if user_id is None:
        return {}
        
    db = get_db()
    rows = db.execute(
        "SELECT item, used_count FROM item_usage WHERE user_id = ?", 
        (user_id,)
    ).fetchall()
    return {row["item"]: row["used_count"] for row in rows}


def get_top_used_items(usage_counts, limit=8):
    """Get the most frequently used items."""
    ranked = sorted(
        ((name, count) for name, count in usage_counts.items() if name in ITEM_INDEX),
        key=lambda pair: (-pair[1], ITEM_INDEX[pair[0]].get("display", pair[0])),
    )
    top = []
    for name, count in ranked[:limit]:
        entry = {**ITEM_INDEX[name], "used_count": count}
        top.append(entry)
    return top


def build_item_catalog(user_id: Optional[int] = None):
    """Return ordered item categories with optional usage data for a specific user."""
    usage_counts = fetch_usage_counts(user_id)
    catalog = OrderedDict()

    top_items = get_top_used_items(usage_counts)
    if top_items:
        catalog["Most Used"] = top_items

    for category, items in ITEMS.items():
        catalog[category] = []
        for item in items:
            entry = dict(item)
            used = usage_counts.get(item["name"])
            if used:
                entry["used_count"] = used
            catalog[category].append(entry)
    return catalog


def delete_item_usage(user_id: int, item_name):
    """Delete usage record for an item for a specific user."""
    db = get_db()
    db.execute("DELETE FROM item_usage WHERE item = ? AND user_id = ?", (item_name, user_id))
    db.commit()

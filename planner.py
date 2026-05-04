import json
import random
from datetime import datetime, timedelta
from db import get_all_recipes, get_recent_meal_plans, get_recipe


def _parse_json_field(val):
    if isinstance(val, list):
        return val
    try:
        return json.loads(val) if val else []
    except Exception:
        return []


def _family_score(recipe):
    kim = recipe.get("rating_kim")
    todd = recipe.get("rating_todd")
    owen = recipe.get("rating_owen")
    if kim is None and todd is None and owen is None:
        return 3.0
    scores = []
    weights = []
    if kim is not None:
        scores.append(kim * 1.5)
        weights.append(1.5)
    if todd is not None:
        scores.append(todd * 1.0)
        weights.append(1.0)
    if owen is not None:
        scores.append(owen * 1.0)
        weights.append(1.0)
    return sum(scores) / sum(weights)


def _recently_made_ids(weeks=3):
    cutoff = (datetime.now() - timedelta(weeks=weeks)).date().isoformat()
    all_recipes = get_all_recipes()
    ids = set()
    for r in all_recipes:
        lm = r.get("last_made")
        if lm and lm >= cutoff:
            ids.add(r["id"])
    return ids


def _last_week_proteins():
    plans = get_recent_meal_plans(1)
    if not plans:
        return set()
    last = plans[0]
    ids = _parse_json_field(last.get("recipe_ids", "[]"))
    proteins = set()
    for rid in ids:
        r = get_recipe(rid)
        if r:
            proteins.update(_parse_json_field(r.get("protein", "[]")))
    return proteins


def suggest_meals(count=5, avoid_proteins=None, require_tags=None, category_set_id="weeknight_dinners"):
    avoid_proteins = set(avoid_proteins or [])
    require_tags = set(require_tags or [])

    all_recipes = get_all_recipes()
    recently_made = _recently_made_ids(weeks=3)
    last_week_proteins = _last_week_proteins()

    candidates = []
    for r in all_recipes:
        if r["id"] in recently_made:
            continue
        proteins = set(_parse_json_field(r.get("protein", "[]")))
        if avoid_proteins and proteins & avoid_proteins:
            continue
        candidates.append(r)

    if not candidates:
        candidates = [r for r in all_recipes if r["id"] not in recently_made]

    # Separate required-tag candidates
    required_picks = []
    if require_tags:
        for r in candidates:
            tags = set(_parse_json_field(r.get("tags", "[]")))
            if tags & require_tags:
                required_picks.append(r)

    # Score all candidates
    def score(r):
        base = _family_score(r)
        proteins = set(_parse_json_field(r.get("protein", "[]")))
        # Slight penalty for repeating last week's protein unless nothing else available
        if proteins & last_week_proteins:
            base -= 0.5
        # Slight bonus for higher times_made (proven winner) but not too much
        base += min(r.get("times_made", 0), 5) * 0.05
        # Add small random jitter for variety across runs
        base += random.uniform(0, 0.3)
        return base

    candidates.sort(key=score, reverse=True)

    chosen = []
    used_proteins = []
    used_methods = []
    slow_cooker_count = 0

    # First, fill required-tag slot(s)
    if require_tags and required_picks:
        required_picks.sort(key=score, reverse=True)
        pick = required_picks[0]
        chosen.append(pick)
        used_proteins.extend(_parse_json_field(pick.get("protein", "[]")))
        used_methods.extend(_parse_json_field(pick.get("cook_method", "[]")))
        if "slow_cooker" in _parse_json_field(pick.get("cook_method", "[]")):
            slow_cooker_count += 1
        candidates = [r for r in candidates if r["id"] != pick["id"]]

    for r in candidates:
        if len(chosen) >= count:
            break

        methods = _parse_json_field(r.get("cook_method", "[]"))
        is_slow_cooker = "slow_cooker" in methods

        # Don't load up on slow cooker (max 2 per week)
        if is_slow_cooker and slow_cooker_count >= 2:
            continue

        # Try to vary proteins: avoid same protein 3+ times in one week
        proteins = _parse_json_field(r.get("protein", "[]"))
        if proteins:
            protein_count = sum(used_proteins.count(p) for p in proteins)
            if protein_count >= 2 and len(chosen) < count - 1:
                continue

        chosen.append(r)
        used_proteins.extend(proteins)
        used_methods.extend(methods)
        if is_slow_cooker:
            slow_cooker_count += 1

    # If we still need more meals (constraints were too tight), fill without restrictions
    if len(chosen) < count:
        remaining = [r for r in candidates if r["id"] not in {c["id"] for c in chosen}]
        remaining.sort(key=score, reverse=True)
        for r in remaining:
            if len(chosen) >= count:
                break
            chosen.append(r)

    return chosen[:count]


def format_suggestion(recipes, week_of=None):
    if not week_of:
        # Next Monday
        today = datetime.now().date()
        days_ahead = (7 - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        week_of = (today + timedelta(days=days_ahead)).isoformat()

    lines = [f"\nSuggested meals for week of {week_of}:\n"]
    for i, r in enumerate(recipes, 1):
        proteins = _parse_json_field(r.get("protein", "[]"))
        methods = _parse_json_field(r.get("cook_method", "[]"))
        sides = _parse_json_field(r.get("sides", "[]"))
        style = r.get("style", "")
        score = _family_score(r)
        score_str = f"  ★{score:.1f}" if score != 3.0 else ""

        protein_str = ", ".join(proteins) if proteins else "meatless"
        method_str = ", ".join(methods)
        sides_str = ", ".join(sides[:3]) if sides else "—"

        lines.append(
            f"  {i}. {r['name']} ({style}) — {protein_str} | {method_str} | {sides_str}{score_str}"
        )
    return "\n".join(lines), week_of

import json
import re
from collections import defaultdict
from db import get_recipe, get_global_substitutions

SECTION_KEYWORDS = {
    "Meat & Protein": [
        "chicken", "beef", "steak", "pork", "sausage", "turkey", "salmon", "shrimp",
        "ground", "tenderloins", "thighs", "breasts", "chops", "roast", "loin",
        "pepperoni", "bacon", "ham", "chorizo", "brats", "bratwurst", "meatball",
        "rotisserie", "italian sausage", "smoked sausage",
    ],
    "Produce": [
        "onion", "garlic", "pepper", "tomato", "lettuce", "spinach", "kale",
        "avocado", "lime", "lemon", "cilantro", "parsley", "basil", "mushroom",
        "zucchini", "squash", "cucumber", "celery", "carrot", "potato", "broccoli",
        "cabbage", "jalapen", "ginger", "apple", "pineapple", "mango", "orange",
        "berry", "berries", "fruit", "vegetable", "salad greens", "salad kit",
        "green onion", "scallion", "radish", "corn on the cob", "fresh herb",
    ],
    "Dairy": [
        "cheese", "cream cheese", "sour cream", "milk", "butter", "yogurt",
        "parmesan", "mozzarella", "ricotta", "cheddar", "monterey", "feta",
        "italian cheese", "colby", "cream", "half and half",
    ],
    "Frozen": [
        "frozen", "ice cream",
    ],
    "Canned/Pantry": [
        "can ", "canned", "broth", "sauce", "salsa", "paste", "diced tomato",
        "tomato sauce", "enchilada", "taco seasoning", "seasoning", "spice",
        "oil", "vinegar", "sugar", "salt", "pepper", "flour", "cornstarch",
        "soy sauce", "worcestershire", "teriyaki", "honey", "mustard", "mayo",
        "ranch", "dressing", "coconut milk", "coconut aminos", "sriracha",
        "hot sauce", "beans", "corn", "olives", "artichoke", "sun-dried",
        "dried", "powder", "cumin", "paprika", "oregano", "thyme", "rosemary",
        "chili powder", "garlic powder", "onion powder", "red pepper flake",
        "bouillon", "noodle", "pasta", "spaghetti", "orzo", "rice steamer",
        "tortilla chip", "crouton",
    ],
    "Bread/Grains": [
        "tortilla", "bread", "roll", "bun", "wrap", "pita", "naan",
        "rice", "quinoa", "pasta", "orzo", "noodle", "spaghetti",
        "toast", "bagel", "english muffin", "taco shell", "tostada",
        "waffle", "hot dog bun",
    ],
    "Refrigerated/Deli": [
        "egg", "tofu", "hummus", "refrigerated", "deli", "crescent",
        "biscuit dough", "pizza dough", "pie crust", "wonton",
    ],
}

SECTION_ORDER = [
    "Meat & Protein",
    "Produce",
    "Dairy",
    "Frozen",
    "Canned/Pantry",
    "Bread/Grains",
    "Refrigerated/Deli",
    "Other",
]


def _classify_ingredient(ingredient_str):
    lower = ingredient_str.lower()
    for section, keywords in SECTION_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return section
    return "Other"


def _apply_substitutions(ingredient_str, global_subs, recipe_subs=None):
    result = ingredient_str
    all_subs = list(global_subs)
    if recipe_subs:
        all_subs.extend(recipe_subs)
    for sub in all_subs:
        # Parse "Substitute X for Y" or "Use X"
        m = re.match(r"substitute (.+?) for (.+)", sub, re.IGNORECASE)
        if m:
            replacement, original = m.group(1).strip(), m.group(2).strip()
            result = re.sub(re.escape(original), replacement, result, flags=re.IGNORECASE)
        # "Use X" substitutions applied at display level (noted in footer)
    return result


def _parse_json_field(val):
    if isinstance(val, list):
        return val
    try:
        return json.loads(val) if val else []
    except Exception:
        return []


def build_shopping_list(recipe_ids):
    global_subs = get_global_substitutions()
    sections = defaultdict(list)
    applied_subs = set()

    for rid in recipe_ids:
        recipe = get_recipe(rid)
        if not recipe:
            continue
        name = recipe["name"]
        recipe_subs = _parse_json_field(recipe.get("substitutions", "[]"))
        all_ingredients = (
            _parse_json_field(recipe.get("assembly_ingredients", "[]"))
            + _parse_json_field(recipe.get("cooking_day_ingredients", "[]"))
        )

        for ing in all_ingredients:
            original = ing
            subbed = _apply_substitutions(ing, global_subs, recipe_subs)
            if subbed != original:
                applied_subs.add(subbed)
            section = _classify_ingredient(subbed)
            sections[section].append((subbed, name))

    # Deduplicate: combine items that appear identical across recipes
    deduped = {}
    for section, items in sections.items():
        merged = defaultdict(list)
        for item, source in items:
            key = re.sub(r"^\d[\d./]*\s*\w*\s*", "", item.lower()).strip()
            merged[key].append((item, source))
        deduped[section] = merged

    return deduped, list(applied_subs), global_subs


def format_shopping_list(recipe_ids, week_of=None):
    deduped, applied_subs, global_subs = build_shopping_list(recipe_ids)
    header = f"Shopping List"
    if week_of:
        header += f" — Week of {week_of}"
    lines = [f"\n{header}", "=" * len(header)]

    for section in SECTION_ORDER:
        if section not in deduped:
            continue
        lines.append(f"\n{section.upper()}")
        for key, entries in deduped[section].items():
            if len(entries) == 1:
                item, source = entries[0]
                lines.append(f"  - {item}  ({source})")
            else:
                # Multiple recipes use this item — show first instance with note
                item = entries[0][0]
                sources = list(dict.fromkeys(s for _, s in entries))
                lines.append(f"  - {item}  [x{len(entries)} — {', '.join(sources)}]")

    if applied_subs or global_subs:
        lines.append("\n[substitutions applied: " + "; ".join(global_subs) + "]")

    return "\n".join(lines)

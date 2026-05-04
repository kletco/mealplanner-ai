import json
import re
from shopping import build_shopping_list, SECTION_ORDER
from db import get_global_substitutions


def _strip_quantity(ingredient_str):
    # Remove leading quantities like "2 lbs", "1 C", "0.5 t", "3-4", "1 pkg"
    # Unit must be followed by a word boundary so "18 chicken" doesn't eat "c" and "1 can X" doesn't eat "can"
    cleaned = re.sub(
        r"^\d[\d./\-]*\s*(lbs?|oz|C|T|tsp|tbsp|cups?|pkg|bags?|bunch|head|cloves?|pieces?|slices?|jar|bottle|box|pints?|quarts?|gallon|lb|g|kg|ml|l)\b\.?\s*",
        "",
        ingredient_str,
        flags=re.IGNORECASE,
    ).strip()
    # Remove parenthetical notes like "(rotisserie recommended)"
    cleaned = re.sub(r"\s*\(.*?\)", "", cleaned).strip()
    return cleaned


def _to_search_query(ingredient_str):
    cleaned = _strip_quantity(ingredient_str)
    # Remove trailing qualifiers that aren't useful for search
    cleaned = re.sub(r",.*$", "", cleaned).strip()
    # Capitalize words
    return " ".join(w.capitalize() for w in cleaned.split())


def format_instacart_list(recipe_ids, week_of=None):
    deduped, applied_subs, global_subs = build_shopping_list(recipe_ids)

    header = "Instacart Shopping List"
    if week_of:
        header += f" — Week of {week_of}"
    lines = [f"\n{header}", "=" * len(header)]
    lines.append("(Search queries formatted for Instacart entry)\n")

    total = 0
    for section in SECTION_ORDER:
        if section not in deduped:
            continue
        lines.append(f"--- {section} ---")
        for key, entries in deduped[section].items():
            item = entries[0][0]
            query = _to_search_query(item)
            if not query:
                continue
            note = ""
            if len(entries) > 1:
                note = f"  # needed for {len(entries)} recipes"
            lines.append(f"  {query}{note}")
            total += 1
        lines.append("")

    lines.append(f"Total items: {total}")
    if global_subs:
        lines.append("\n[Global substitutions applied]:")
        for sub in global_subs:
            lines.append(f"  • {sub}")

    return "\n".join(lines)

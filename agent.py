"""
Claude-powered natural language interface with tool use.
Requires ANTHROPIC_API_KEY environment variable.
"""
import json
import os
from datetime import datetime
from db import (get_all_recipes, get_global_substitutions, get_recent_meal_plans,
                get_recipe, update_recipe, get_all_recipes)
from planner import _parse_json_field, _family_score

try:
    import anthropic
    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False


SYSTEM_PROMPT = """You are a meal planning assistant for a family of 3 (Kim, Todd, and Owen).
You have access to their recipe database via tools. Help them plan dinners, record what they made, log ratings, and answer questions.

Family preferences:
- Kim prefers high-protein, lower-carb meals and clean eating (CE style)
- Owen (born 2013) likes kid-friendly classics
- They prefer variety in protein across the week
- Kim substitutes jasmine rice for cauliflower rice; uses Carb Balance tortillas
- They shop at Wegmans via Instacart pickup

When the user says they made a recipe or asks you to mark one as done, ALWAYS call mark_done.
When the user gives ratings, ALWAYS call set_ratings.
When searching for a recipe by name, use search_recipes first to find the correct ID.
After using a tool, briefly confirm what you did."""


TOOLS = [
    {
        "name": "search_recipes",
        "description": "Search recipes by name, protein, style, cook method, or tag. Returns matching recipes with their IDs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Partial name to search (case-insensitive)"},
                "protein": {"type": "string", "description": "Filter by protein: beef, poultry, pork, meatless"},
                "style": {"type": "string", "description": "Filter by style: CE, C, Skillet2"},
                "tag": {"type": "string", "description": "Filter by tag e.g. slow_cooker, freezable, kid_favorite"},
                "method": {"type": "string", "description": "Filter by cook method: oven, slow_cooker, grill, stovetop"},
            },
            "required": [],
        },
    },
    {
        "name": "get_recipe_detail",
        "description": "Get full details for a specific recipe by ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "recipe_id": {"type": "string", "description": "The recipe ID"},
            },
            "required": ["recipe_id"],
        },
    },
    {
        "name": "mark_done",
        "description": "Mark a recipe as made today. Updates last_made to today's date and increments times_made.",
        "input_schema": {
            "type": "object",
            "properties": {
                "recipe_id": {"type": "string", "description": "The recipe ID to mark as done"},
            },
            "required": ["recipe_id"],
        },
    },
    {
        "name": "set_ratings",
        "description": "Set Kim, Todd, and/or Owen's rating (1-5) for a recipe. Omit a person to leave their rating unchanged.",
        "input_schema": {
            "type": "object",
            "properties": {
                "recipe_id": {"type": "string", "description": "The recipe ID"},
                "rating_kim":  {"type": "integer", "minimum": 1, "maximum": 5, "description": "Kim's rating 1-5"},
                "rating_todd": {"type": "integer", "minimum": 1, "maximum": 5, "description": "Todd's rating 1-5"},
                "rating_owen": {"type": "integer", "minimum": 1, "maximum": 5, "description": "Owen's rating 1-5"},
            },
            "required": ["recipe_id"],
        },
    },
    {
        "name": "add_note",
        "description": "Add or update a note on a recipe.",
        "input_schema": {
            "type": "object",
            "properties": {
                "recipe_id": {"type": "string", "description": "The recipe ID"},
                "note": {"type": "string", "description": "The note text to set"},
            },
            "required": ["recipe_id", "note"],
        },
    },
    {
        "name": "list_recent",
        "description": "List the most recently made recipes or recent meal plans.",
        "input_schema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "How many recent items to return (default 5)"},
            },
            "required": [],
        },
    },
]


def _run_tool(name, inputs):
    if name == "search_recipes":
        recipes = get_all_recipes()
        results = []
        for r in recipes:
            if inputs.get("name") and inputs["name"].lower() not in r["name"].lower():
                continue
            if inputs.get("protein") and inputs["protein"] not in _parse_json_field(r.get("protein", "[]")):
                continue
            if inputs.get("style") and r.get("style", "").upper() != inputs["style"].upper():
                continue
            if inputs.get("tag"):
                all_tags = set(_parse_json_field(r.get("tags","[]"))) | set(_parse_json_field(r.get("custom_tags","[]")))
                if inputs["tag"] not in all_tags:
                    continue
            if inputs.get("method") and inputs["method"] not in _parse_json_field(r.get("cook_method","[]")):
                continue
            results.append({
                "id": r["id"],
                "name": r["name"],
                "style": r.get("style"),
                "protein": _parse_json_field(r.get("protein","[]")),
                "cook_method": _parse_json_field(r.get("cook_method","[]")),
                "last_made": r.get("last_made"),
                "times_made": r.get("times_made", 0),
                "rating_kim": r.get("rating_kim"),
                "rating_todd": r.get("rating_todd"),
                "rating_owen": r.get("rating_owen"),
            })
        return {"count": len(results), "recipes": results[:20]}

    elif name == "get_recipe_detail":
        r = get_recipe(inputs["recipe_id"])
        if not r:
            return {"error": f"Recipe '{inputs['recipe_id']}' not found"}
        for field in ("protein","tags","cook_method","sides","assembly_ingredients",
                      "cooking_day_ingredients","custom_tags","substitutions"):
            if isinstance(r.get(field), str):
                try:
                    r[field] = json.loads(r[field])
                except Exception:
                    r[field] = []
        return r

    elif name == "mark_done":
        r = get_recipe(inputs["recipe_id"])
        if not r:
            return {"error": f"Recipe '{inputs['recipe_id']}' not found"}
        today = datetime.now().date().isoformat()
        new_count = (r.get("times_made") or 0) + 1
        update_recipe(inputs["recipe_id"], {"last_made": today, "times_made": new_count})
        return {"ok": True, "recipe": r["name"], "last_made": today, "times_made": new_count}

    elif name == "set_ratings":
        r = get_recipe(inputs["recipe_id"])
        if not r:
            return {"error": f"Recipe '{inputs['recipe_id']}' not found"}
        fields = {}
        for person in ("kim", "todd", "owen"):
            key = f"rating_{person}"
            if key in inputs:
                fields[key] = inputs[key]
        update_recipe(inputs["recipe_id"], fields)
        return {"ok": True, "recipe": r["name"], "updated_ratings": fields}

    elif name == "add_note":
        r = get_recipe(inputs["recipe_id"])
        if not r:
            return {"error": f"Recipe '{inputs['recipe_id']}' not found"}
        update_recipe(inputs["recipe_id"], {"notes": inputs["note"]})
        return {"ok": True, "recipe": r["name"], "note": inputs["note"]}

    elif name == "list_recent":
        count = inputs.get("count", 5)
        recipes = get_all_recipes()
        made = [r for r in recipes if r.get("last_made")]
        made.sort(key=lambda r: r["last_made"] or "", reverse=True)
        return {
            "recently_made": [
                {"id": r["id"], "name": r["name"], "last_made": r["last_made"],
                 "times_made": r["times_made"], "family_score": round(_family_score(r), 1)}
                for r in made[:count]
            ]
        }

    return {"error": f"Unknown tool: {name}"}


def _build_recipe_list():
    """Compact recipe list for the system prompt context."""
    recipes = get_all_recipes()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "style": r.get("style"),
            "protein": _parse_json_field(r.get("protein","[]")),
            "cook_method": _parse_json_field(r.get("cook_method","[]")),
            "tags": _parse_json_field(r.get("tags","[]")),
            "last_made": r.get("last_made"),
            "times_made": r.get("times_made", 0),
            "rating_kim": r.get("rating_kim"),
            "rating_todd": r.get("rating_todd"),
            "rating_owen": r.get("rating_owen"),
        }
        for r in recipes
    ]


def chat(user_message, history=None):
    if not _HAS_ANTHROPIC:
        return "Error: anthropic package not installed. Run: pip install anthropic", history or []

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return "Error: ANTHROPIC_API_KEY environment variable not set.", history or []

    client = anthropic.Anthropic(api_key=api_key)

    recipe_list = _build_recipe_list()
    system = SYSTEM_PROMPT + f"\n\nRecipe database ({len(recipe_list)} recipes):\n{json.dumps(recipe_list)}"

    messages = list(history or [])
    messages.append({"role": "user", "content": user_message})

    # Agentic loop — keep going until no more tool calls
    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

        # Collect all content blocks
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            # Extract final text reply
            text = next((b.text for b in response.content if hasattr(b, "text")), "")
            return text, messages

        # Process tool calls
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = _run_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                })

        messages.append({"role": "user", "content": tool_results})


def run_chat_loop():
    if not _HAS_ANTHROPIC:
        print("anthropic package not installed. Run: pip install anthropic")
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set.")
        return

    print("Meal Planner Chat — type 'quit' to exit")
    print("You can say things like: 'We made the chicken fajitas tonight', 'Rate huli huli 5/5/4', 'What did we last make?'\n")
    history = []
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user_input.lower() in ("quit", "exit", "q"):
            break
        if not user_input:
            continue
        reply, history = chat(user_input, history)
        print(f"\nAssistant: {reply}\n")

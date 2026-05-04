#!/usr/bin/env python3
import sys
import os
import json
import click
from datetime import datetime, timedelta

# Ensure mealplanner/ is on the path when invoked directly
sys.path.insert(0, os.path.dirname(__file__))

import db as _db
from planner import suggest_meals, format_suggestion, _parse_json_field, _family_score
from shopping import format_shopping_list
from instacart import format_instacart_list


def _next_monday():
    today = datetime.now().date()
    days = (7 - today.weekday()) % 7
    if days == 0:
        days = 7
    return (today + timedelta(days=days)).isoformat()


def _resolve_week(week_str):
    if not week_str:
        return _next_monday()
    # Accept "this", "next", or ISO date
    if week_str.lower() == "this":
        today = datetime.now().date()
        return (today - timedelta(days=today.weekday())).isoformat()
    if week_str.lower() == "next":
        return _next_monday()
    return week_str


@click.group()
def cli():
    """Meal Planner — weekly dinner planning for Kim, Todd & Owen."""
    pass


# ── db ────────────────────────────────────────────────────────────────────────

@cli.group()
def db():
    """Database management commands."""
    pass


@db.command("init")
def db_init():
    """Create the database and seed from recipes_seed.json."""
    _db.init_db()
    _db.seed_db()


# ── plan ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--count", default=5, show_default=True, help="Number of meals to suggest.")
@click.option("--avoid", multiple=True, metavar="PROTEIN", help="Protein(s) to exclude (repeatable).")
@click.option("--require", multiple=True, metavar="TAG", help="Require at least one meal with this tag.")
@click.option("--category", default="weeknight_dinners", show_default=True, help="Category set ID.")
@click.option("--week", default=None, metavar="DATE", help="Week-of date (ISO, 'this', or 'next').")
def plan(count, avoid, require, category, week):
    """Suggest a weekly dinner menu."""
    week_of = _resolve_week(week)
    recipes = suggest_meals(
        count=count,
        avoid_proteins=list(avoid),
        require_tags=list(require),
        category_set_id=category,
    )
    if not recipes:
        click.echo("No recipes found matching your criteria.")
        return

    output, week_of = format_suggestion(recipes, week_of)
    click.echo(output)

    answer = click.prompt("\nAccept these suggestions? [y/n/edit]", default="y")
    if answer.lower() == "y":
        recipe_ids = [r["id"] for r in recipes]
        _db.save_meal_plan(week_of, recipe_ids, category_set_id=category)
        click.echo(f"Week saved. Run 'mealplan list --week {week_of}' to see your shopping list.")
    elif answer.lower() == "edit":
        click.echo("Edit mode: enter recipe IDs to keep (comma-separated), or press Enter to keep all:")
        kept_input = click.prompt("Keep IDs", default="")
        if kept_input.strip():
            kept_ids = [x.strip() for x in kept_input.split(",")]
            recipes = [r for r in recipes if r["id"] in kept_ids]
        recipe_ids = [r["id"] for r in recipes]
        _db.save_meal_plan(week_of, recipe_ids, category_set_id=category)
        click.echo(f"Week saved with {len(recipe_ids)} meals.")
    else:
        click.echo("Suggestions discarded.")


# ── list ──────────────────────────────────────────────────────────────────────

@cli.command("list")
@click.argument("week", default=None, required=False)
def list_shopping(week):
    """Show the shopping list for a planned week."""
    week_of = _resolve_week(week)
    meal_plan = _db.get_meal_plan(week_of)
    if not meal_plan:
        click.echo(f"No meal plan found for week of {week_of}.")
        click.echo("Run 'mealplan plan' first, or specify a week: mealplan list 2026-04-28")
        return
    recipe_ids = _parse_json_field(meal_plan.get("recipe_ids", "[]"))
    output = format_shopping_list(recipe_ids, week_of)
    click.echo(output)


# ── rate ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("recipe_id")
def rate(recipe_id):
    """Interactively rate a recipe (Kim, Todd, Owen on 1-5 scale)."""
    recipe = _db.get_recipe(recipe_id)
    if not recipe:
        click.echo(f"Recipe '{recipe_id}' not found.")
        return
    click.echo(f"\nRating: {recipe['name']}")
    fields = {}
    for person in ("kim", "todd", "owen"):
        current = recipe.get(f"rating_{person}")
        current_str = f" (current: {current})" if current else ""
        val = click.prompt(f"  {person.capitalize()}'s rating (1-5, Enter to skip){current_str}", default="", show_default=False)
        if val.strip():
            try:
                fields[f"rating_{person}"] = int(val)
            except ValueError:
                click.echo(f"  Invalid rating for {person}, skipping.")
    if fields:
        _db.update_recipe(recipe_id, fields)
        click.echo("Ratings saved.")
    else:
        click.echo("No changes made.")


# ── add ───────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--from-json", "json_path", default=None, metavar="FILE", help="Load recipe from JSON file.")
def add(json_path):
    """Add a new recipe to the database."""
    if json_path:
        with open(json_path) as f:
            r = json.load(f)
        _db.add_recipe(r)
        click.echo(f"Added recipe: {r['name']} (id: {r['id']})")
        return

    click.echo("Add a new recipe interactively.\n")
    r = {}
    r["id"] = click.prompt("ID (short unique key, e.g. 'X_fav')")
    if _db.get_recipe(r["id"]):
        click.echo(f"Recipe ID '{r['id']}' already exists.")
        return
    r["name"] = click.prompt("Name")
    r["style"] = click.prompt("Style (CE/C/Skillet2)", default="C")
    r["protein"] = [p.strip() for p in click.prompt("Protein(s) (comma-separated)", default="").split(",") if p.strip()]
    r["tags"] = [t.strip() for t in click.prompt("Tags (comma-separated)", default="").split(",") if t.strip()]
    r["cook_method"] = [m.strip() for m in click.prompt("Cook method(s) (comma-separated)", default="oven").split(",") if m.strip()]
    r["sides"] = [s.strip() for s in click.prompt("Sides (comma-separated)", default="").split(",") if s.strip()]
    r["notes"] = click.prompt("Notes", default="")
    r["source"] = click.prompt("Source", default="5dinners1hour")

    click.echo("\nAssembly ingredients (one per line, blank line to finish):")
    r["assembly_ingredients"] = []
    while True:
        ing = input("  > ").strip()
        if not ing:
            break
        r["assembly_ingredients"].append(ing)

    click.echo("\nCooking day ingredients (one per line, blank line to finish):")
    r["cooking_day_ingredients"] = []
    while True:
        ing = input("  > ").strip()
        if not ing:
            break
        r["cooking_day_ingredients"].append(ing)

    r["times_made"] = 0
    r["custom_tags"] = []
    r["substitutions"] = []
    _db.add_recipe(r)
    click.echo(f"\nAdded recipe: {r['name']} (id: {r['id']})")


# ── update ────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("recipe_id")
@click.option("--notes", default=None)
@click.option("--last-made", default=None, metavar="DATE")
@click.option("--times-made", default=None, type=int)
@click.option("--add-tag", multiple=True, metavar="TAG")
@click.option("--add-sub", multiple=True, metavar="SUBSTITUTION")
@click.option("--active/--inactive", default=None)
def update(recipe_id, notes, last_made, times_made, add_tag, add_sub, active):
    """Update fields on a recipe."""
    recipe = _db.get_recipe(recipe_id)
    if not recipe:
        click.echo(f"Recipe '{recipe_id}' not found.")
        return
    fields = {}
    if notes is not None:
        fields["notes"] = notes
    if last_made is not None:
        fields["last_made"] = last_made
    if times_made is not None:
        fields["times_made"] = times_made
    if active is not None:
        fields["active"] = 1 if active else 0
    if add_tag:
        existing = _parse_json_field(recipe.get("custom_tags", "[]"))
        fields["custom_tags"] = list(set(existing) | set(add_tag))
    if add_sub:
        existing = _parse_json_field(recipe.get("substitutions", "[]"))
        fields["substitutions"] = existing + list(add_sub)
    if fields:
        _db.update_recipe(recipe_id, fields)
        click.echo(f"Updated {recipe_id}: {', '.join(fields.keys())}")
    else:
        click.echo("No changes specified. Use --help to see options.")


# ── done ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("recipe_id")
def done(recipe_id):
    """Mark a recipe as made today."""
    recipe = _db.get_recipe(recipe_id)
    if not recipe:
        click.echo(f"Recipe '{recipe_id}' not found.")
        return
    today = datetime.now().date().isoformat()
    new_count = (recipe.get("times_made") or 0) + 1
    _db.update_recipe(recipe_id, {"last_made": today, "times_made": new_count})
    click.echo(f"Marked '{recipe['name']}' as made on {today} (total times: {new_count}).")


# ── search ────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--protein", default=None, metavar="TYPE", help="Filter by protein type.")
@click.option("--tag", default=None, metavar="TAG", help="Filter by tag.")
@click.option("--style", default=None, metavar="STYLE", help="Filter by style (CE/C/Skillet2).")
@click.option("--name", default=None, metavar="TEXT", help="Search name (case-insensitive substring).")
@click.option("--method", default=None, metavar="METHOD", help="Filter by cook method.")
@click.option("--min-rating-kim", default=None, type=int, metavar="N", help="Minimum Kim rating.")
@click.option("--min-rating-todd", default=None, type=int, metavar="N")
@click.option("--min-rating-owen", default=None, type=int, metavar="N")
def search(protein, tag, style, name, method, min_rating_kim, min_rating_todd, min_rating_owen):
    """Search and filter recipes."""
    recipes = _db.get_all_recipes()
    results = []
    for r in recipes:
        if protein and protein not in _parse_json_field(r.get("protein", "[]")):
            continue
        if tag:
            all_tags = set(_parse_json_field(r.get("tags", "[]"))) | set(_parse_json_field(r.get("custom_tags", "[]")))
            if tag not in all_tags:
                continue
        if style and r.get("style", "").upper() != style.upper():
            continue
        if name and name.lower() not in r["name"].lower():
            continue
        if method and method not in _parse_json_field(r.get("cook_method", "[]")):
            continue
        if min_rating_kim and (r.get("rating_kim") or 0) < min_rating_kim:
            continue
        if min_rating_todd and (r.get("rating_todd") or 0) < min_rating_todd:
            continue
        if min_rating_owen and (r.get("rating_owen") or 0) < min_rating_owen:
            continue
        results.append(r)

    if not results:
        click.echo("No recipes found.")
        return

    click.echo(f"\n{len(results)} recipe(s) found:\n")
    for r in results:
        proteins = ", ".join(_parse_json_field(r.get("protein", "[]"))) or "meatless"
        methods = ", ".join(_parse_json_field(r.get("cook_method", "[]")))
        score = _family_score(r)
        score_str = f"  ★{score:.1f}" if (r.get("rating_kim") or r.get("rating_todd") or r.get("rating_owen")) else ""
        click.echo(f"  [{r['id']}] {r['name']} ({r.get('style','')}) — {proteins} | {methods}{score_str}")


# ── show ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("recipe_id")
def show(recipe_id):
    """Display full recipe details."""
    r = _db.get_recipe(recipe_id)
    if not r:
        click.echo(f"Recipe '{recipe_id}' not found.")
        return

    click.echo(f"\n{'='*50}")
    click.echo(f"  {r['name']}")
    click.echo(f"{'='*50}")
    click.echo(f"  ID: {r['id']}  |  Style: {r.get('style','')}  |  Source: {r.get('source','')}")
    click.echo(f"  Protein: {', '.join(_parse_json_field(r.get('protein','[]'))) or 'meatless'}")
    click.echo(f"  Cook method: {', '.join(_parse_json_field(r.get('cook_method','[]')))}")
    click.echo(f"  Tags: {', '.join(_parse_json_field(r.get('tags','[]')))}")

    custom = _parse_json_field(r.get("custom_tags", "[]"))
    if custom:
        click.echo(f"  Custom tags: {', '.join(custom)}")

    sides = _parse_json_field(r.get("sides", "[]"))
    if sides:
        click.echo(f"  Sides: {', '.join(sides)}")

    click.echo(f"\n  Ratings: Kim={r.get('rating_kim','—')}  Todd={r.get('rating_todd','—')}  Owen={r.get('rating_owen','—')}")
    score = _family_score(r)
    click.echo(f"  Family score: {score:.1f} / 5.0")

    click.echo(f"\n  Last made: {r.get('last_made') or 'never'}  |  Times made: {r.get('times_made', 0)}")

    asm = _parse_json_field(r.get("assembly_ingredients", "[]"))
    if asm:
        click.echo(f"\n  ASSEMBLY INGREDIENTS:")
        for ing in asm:
            click.echo(f"    - {ing}")

    cook = _parse_json_field(r.get("cooking_day_ingredients", "[]"))
    if cook:
        click.echo(f"\n  COOKING DAY INGREDIENTS:")
        for ing in cook:
            click.echo(f"    - {ing}")

    subs = _parse_json_field(r.get("substitutions", "[]"))
    if subs:
        click.echo(f"\n  PERSONAL SUBSTITUTIONS:")
        for s in subs:
            click.echo(f"    • {s}")

    notes = r.get("notes", "")
    if notes:
        click.echo(f"\n  NOTES: {notes}")

    click.echo("")


# ── instacart ─────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("week", default=None, required=False)
def instacart(week):
    """Generate an Instacart-formatted shopping list."""
    week_of = _resolve_week(week)
    meal_plan = _db.get_meal_plan(week_of)
    if not meal_plan:
        click.echo(f"No meal plan found for week of {week_of}.")
        return
    recipe_ids = _parse_json_field(meal_plan.get("recipe_ids", "[]"))
    output = format_instacart_list(recipe_ids, week_of)
    click.echo(output)


# ── category ──────────────────────────────────────────────────────────────────

@cli.group()
def category():
    """Manage category sets."""
    pass


@category.command("add")
@click.option("--id", "cs_id", required=True, metavar="ID")
@click.option("--name", required=True, metavar="NAME")
@click.option("--description", default="", metavar="DESC")
def category_add(cs_id, name, description):
    """Add a new category set."""
    _db.add_category_set(cs_id, name, description)
    click.echo(f"Category set '{cs_id}' added.")


@category.command("list")
def category_list():
    """List all category sets."""
    sets = _db.list_category_sets()
    if not sets:
        click.echo("No category sets found.")
        return
    for cs in sets:
        click.echo(f"  [{cs['id']}] {cs['name']} — {cs.get('description','')}")


# ── chat ──────────────────────────────────────────────────────────────────────

@cli.command()
def chat():
    """Launch Claude-powered natural language chat interface."""
    from agent import run_chat_loop
    run_chat_loop()


# ── plans ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--count", default=5, show_default=True)
def plans(count):
    """Show recent meal plans."""
    recent = _db.get_recent_meal_plans(count)
    if not recent:
        click.echo("No meal plans saved yet.")
        return
    for p in recent:
        ids = _parse_json_field(p.get("recipe_ids", "[]"))
        names = []
        for rid in ids:
            r = _db.get_recipe(rid)
            names.append(r["name"] if r else rid)
        click.echo(f"\nWeek of {p['week_of']}:")
        for n in names:
            click.echo(f"  • {n}")


if __name__ == "__main__":
    cli()

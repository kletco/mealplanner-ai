import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "mealplanner.db")
SEED_PATH = os.path.join(os.path.dirname(__file__), "..", "seed_file", "recipes_seed.json")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS recipes (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            style TEXT,
            protein TEXT,
            tags TEXT,
            cook_method TEXT,
            sides TEXT,
            assembly_ingredients TEXT,
            cooking_day_ingredients TEXT,
            rating_kim INTEGER,
            rating_todd INTEGER,
            rating_owen INTEGER,
            notes TEXT,
            last_made TEXT,
            times_made INTEGER DEFAULT 0,
            custom_tags TEXT,
            substitutions TEXT,
            source TEXT DEFAULT '5dinners1hour',
            active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS meal_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_of TEXT NOT NULL,
            category_set_id TEXT,
            recipe_ids TEXT,
            notes TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS category_sets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT
        );

        CREATE TABLE IF NOT EXISTS global_substitutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            substitution TEXT NOT NULL
        );
    """)

    conn.commit()
    conn.close()
    print("Database initialized.")


def seed_db():
    if not os.path.exists(SEED_PATH):
        print(f"Seed file not found at {SEED_PATH}")
        return

    with open(SEED_PATH, "r") as f:
        data = json.load(f)

    conn = get_conn()
    c = conn.cursor()

    recipes_inserted = 0
    for r in data.get("recipes", []):
        existing = c.execute("SELECT id FROM recipes WHERE id = ?", (r["id"],)).fetchone()
        if existing:
            continue
        c.execute("""
            INSERT INTO recipes
              (id, name, style, protein, tags, cook_method, sides,
               assembly_ingredients, cooking_day_ingredients,
               rating_kim, rating_todd, rating_owen, notes,
               last_made, times_made, custom_tags, substitutions, source, active)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
        """, (
            r["id"], r["name"], r.get("style"), json.dumps(r.get("protein", [])),
            json.dumps(r.get("tags", [])), json.dumps(r.get("cook_method", [])),
            json.dumps(r.get("sides", [])), json.dumps(r.get("assembly_ingredients", [])),
            json.dumps(r.get("cooking_day_ingredients", [])),
            r.get("rating_kim"), r.get("rating_todd"), r.get("rating_owen"),
            r.get("notes", ""), r.get("last_made"), r.get("times_made", 0),
            json.dumps(r.get("custom_tags", [])), json.dumps(r.get("substitutions", [])),
            r.get("source", "5dinners1hour"),
        ))
        recipes_inserted += 1

    for sub in data.get("global_substitutions", []):
        existing = c.execute("SELECT id FROM global_substitutions WHERE substitution = ?", (sub,)).fetchone()
        if not existing:
            c.execute("INSERT INTO global_substitutions (substitution) VALUES (?)", (sub,))

    for cs in data.get("category_sets", []):
        existing = c.execute("SELECT id FROM category_sets WHERE id = ?", (cs["id"],)).fetchone()
        if not existing:
            c.execute(
                "INSERT INTO category_sets (id, name, description) VALUES (?,?,?)",
                (cs["id"], cs["name"], cs.get("description", "")),
            )

    conn.commit()
    conn.close()
    print(f"Seeded {recipes_inserted} recipes.")


def get_recipe(recipe_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM recipes WHERE id = ? AND active = 1", (recipe_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_recipes(active_only=True):
    conn = get_conn()
    q = "SELECT * FROM recipes" + (" WHERE active = 1" if active_only else "")
    rows = conn.execute(q).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_global_substitutions():
    conn = get_conn()
    rows = conn.execute("SELECT substitution FROM global_substitutions").fetchall()
    conn.close()
    return [r["substitution"] for r in rows]


def update_recipe(recipe_id, fields: dict) -> bool:
    """Update fields on a recipe. Returns True if a row was matched, False if not found."""
    if not fields:
        return True
    conn = get_conn()
    matched = 0
    for key, val in fields.items():
        if isinstance(val, (list, dict)):
            val = json.dumps(val)
        cur = conn.execute(f"UPDATE recipes SET {key} = ? WHERE id = ?", (val, recipe_id))
        matched = max(matched, cur.rowcount)
    conn.commit()
    conn.close()
    return matched > 0


def save_meal_plan(week_of, recipe_ids, category_set_id="weeknight_dinners", notes=""):
    conn = get_conn()
    conn.execute(
        "INSERT INTO meal_plans (week_of, category_set_id, recipe_ids, notes, created_at) VALUES (?,?,?,?,?)",
        (week_of, category_set_id, json.dumps(recipe_ids), notes, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_meal_plan(week_of):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM meal_plans WHERE week_of = ? ORDER BY id DESC LIMIT 1", (week_of,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_recent_meal_plans(n=5):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM meal_plans ORDER BY week_of DESC LIMIT ?", (n,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_recipe(r: dict):
    conn = get_conn()
    conn.execute("""
        INSERT INTO recipes
          (id, name, style, protein, tags, cook_method, sides,
           assembly_ingredients, cooking_day_ingredients,
           rating_kim, rating_todd, rating_owen, notes,
           last_made, times_made, custom_tags, substitutions, source, active)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
    """, (
        r["id"], r["name"], r.get("style"), json.dumps(r.get("protein", [])),
        json.dumps(r.get("tags", [])), json.dumps(r.get("cook_method", [])),
        json.dumps(r.get("sides", [])), json.dumps(r.get("assembly_ingredients", [])),
        json.dumps(r.get("cooking_day_ingredients", [])),
        r.get("rating_kim"), r.get("rating_todd"), r.get("rating_owen"),
        r.get("notes", ""), r.get("last_made"), r.get("times_made", 0),
        json.dumps(r.get("custom_tags", [])), json.dumps(r.get("substitutions", [])),
        r.get("source", "5dinners1hour"),
    ))
    conn.commit()
    conn.close()


def add_category_set(cs_id, name, description=""):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO category_sets (id, name, description) VALUES (?,?,?)",
        (cs_id, name, description),
    )
    conn.commit()
    conn.close()


def list_category_sets():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM category_sets").fetchall()
    conn.close()
    return [dict(r) for r in rows]

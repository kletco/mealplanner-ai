# mealplanner-ai

A personal weekly dinner planning system. Includes a CLI for planning and shopping lists, a web UI for browsing and rating recipes, and a Claude-powered chat agent for natural-language interaction.

## Features

- **Weekly meal planning** — suggests 5 dinners with protein variety, cook method variety, and recency avoidance
- **Shopping list generation** — consolidates ingredients across all recipes, grouped by store section, with substitutions applied
- **Instacart-ready output** — formats the shopping list as search queries
- **Family ratings** — Kim, Todd, and Owen each rate 1–5; family score weights Kim 1.5×
- **Web UI** — browse, filter, sort, and rate recipes; click to edit Last Made dates inline
- **Claude agent** — natural language chat that reads and writes the database (mark as done, set ratings, add notes)

## Setup

**Requirements:** Python 3.10+

```bash
pip install click flask anthropic
```

**Seed data:** This project expects a `recipes_seed.json` file at `../seed_file/recipes_seed.json` (one level above the repo). The seed file is not included — provide your own in this format:

```json
{
  "recipes": [
    {
      "id": "unique_id",
      "name": "Recipe Name",
      "style": "CE",
      "protein": ["poultry"],
      "tags": ["one_pan"],
      "cook_method": ["oven"],
      "sides": ["salad"],
      "assembly_ingredients": ["..."],
      "cooking_day_ingredients": ["..."],
      "notes": "",
      "source": "custom"
    }
  ],
  "global_substitutions": [
    "Substitute X for Y"
  ],
  "category_sets": [
    { "id": "weeknight_dinners", "name": "Weeknight Dinners", "description": "" }
  ]
}
```

Then initialize the database:

```bash
python mealplan.py db init    # creates mealplanner.db and seeds from ../seed_file/recipes_seed.json
```

For the Claude agent, set your Anthropic API key:
```bash
# macOS / Linux
export ANTHROPIC_API_KEY="sk-ant-..."

# Windows (current session)
set ANTHROPIC_API_KEY=sk-ant-...

# Windows (permanent, requires new terminal)
setx ANTHROPIC_API_KEY "sk-ant-..."
```

## Web UI

```bash
python server.py
# Open http://localhost:5000
```

- **Filter bar** — search by name, or filter by style, protein, cook method, or tag
- **Sort** — click any column header
- **Star ratings** — click any star to rate 1–5; click the same star again to clear; saves immediately
- **Last Made** — click any date (or "never") to open a date picker; saves on selection
- **Refresh** (↺) — re-fetches all data; also auto-refreshes when you switch back to the tab

## CLI

```bash
python mealplan.py <command>
```

| Command | Description |
|---------|-------------|
| `plan` | Suggest meals for the week (`--count N`, `--avoid PROTEIN`, `--require TAG`) |
| `list [WEEK]` | Shopping list grouped by store section |
| `instacart [WEEK]` | Instacart-formatted search queries |
| `done RECIPE_ID` | Mark a recipe as made today |
| `rate RECIPE_ID` | Interactively set Kim / Todd / Owen ratings |
| `search` | Filter recipes (`--protein`, `--style`, `--tag`, `--method`, `--name`) |
| `show RECIPE_ID` | Full recipe detail |
| `add` | Add a recipe interactively or `--from-json file.json` |
| `update RECIPE_ID` | Update notes, tags, substitutions, ratings |
| `plans` | Recent meal plan history |
| `category` | Manage category sets |
| `chat` | Claude agent (requires `ANTHROPIC_API_KEY`) |

## Claude Agent

```bash
python mealplan.py chat
```

The agent can search recipes, mark meals as done, set ratings, add notes, and show recent history — it actually writes to the database, not just responds with text.

## Suggestion Logic

- Excludes recipes made in the last 3 weeks
- Avoids repeating last week's dominant protein
- Caps slow cooker meals at 2 per week
- Family score: `(Kim × 1.5 + Todd × 1.0 + Owen × 1.0) / 3.5`
- Unrated recipes score 3.0 (neutral)
- Global substitutions applied automatically on all shopping and Instacart output

## Project Structure

```
mealplanner-ai/
├── mealplan.py      # CLI entry point
├── server.py        # Flask API + static server for web UI
├── index.html       # Single-page web UI
├── db.py            # SQLite setup, seed loader, all DB helpers
├── planner.py       # Meal suggestion and scoring logic
├── shopping.py      # Ingredient consolidation, store-section grouping
├── instacart.py     # Instacart-formatted output
└── agent.py         # Claude tool-use agent
```

`mealplanner.db` is created on first run and excluded from version control.
Seed data (`../seed_file/recipes_seed.json`) is also excluded — provide your own.

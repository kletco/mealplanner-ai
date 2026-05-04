import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify, request, send_from_directory
import db as _db

app = Flask(__name__, static_folder='.', static_url_path='')


def _parse_recipe(r):
    for field in ('protein', 'tags', 'cook_method', 'sides',
                  'assembly_ingredients', 'cooking_day_ingredients',
                  'custom_tags', 'substitutions'):
        val = r.get(field)
        if isinstance(val, str):
            try:
                r[field] = json.loads(val)
            except Exception:
                r[field] = []
    return r


@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/api/recipes')
def get_recipes():
    recipes = _db.get_all_recipes()
    return jsonify([_parse_recipe(dict(r)) for r in recipes])


@app.route('/api/recipes/<recipe_id>', methods=['PATCH'])
def update_recipe_fields(recipe_id):
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'error': 'Invalid or missing JSON body'}), 400

    if _db.get_recipe(recipe_id) is None:
        return jsonify({'error': f'Recipe {recipe_id!r} not found'}), 404

    allowed = {'last_made', 'times_made', 'notes'}
    fields = {k: v for k, v in data.items() if k in allowed}
    if not fields:
        return jsonify({'error': f'No recognised fields. Allowed: {sorted(allowed)}'}), 400

    _db.update_recipe(recipe_id, fields)
    updated = _db.get_recipe(recipe_id)
    return jsonify({'ok': True, 'recipe': _parse_recipe(dict(updated))})


@app.route('/api/recipes/<recipe_id>/ratings', methods=['PATCH'])
def update_ratings(recipe_id):
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'error': 'Invalid or missing JSON body'}), 400

    if _db.get_recipe(recipe_id) is None:
        return jsonify({'error': f'Recipe {recipe_id!r} not found'}), 404

    fields = {}
    for person in ('kim', 'todd', 'owen'):
        key = f'rating_{person}'
        if key not in data:
            continue
        val = data[key]
        if val is None:
            fields[key] = None
        else:
            try:
                rating = int(val)
            except (TypeError, ValueError):
                return jsonify({'error': f'{key} must be an integer 1–5 or null'}), 400
            if not 1 <= rating <= 5:
                return jsonify({'error': f'{key} must be between 1 and 5'}), 400
            fields[key] = rating

    if not fields:
        return jsonify({'error': 'No rating fields provided (rating_kim, rating_todd, rating_owen)'}), 400

    _db.update_recipe(recipe_id, fields)
    updated = _db.get_recipe(recipe_id)
    return jsonify({'ok': True, 'recipe': _parse_recipe(dict(updated))})


if __name__ == '__main__':
    print('Starting Meal Planner UI at http://localhost:5000')
    app.run(debug=True, port=5000)

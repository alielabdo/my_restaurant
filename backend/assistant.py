#!/usr/bin/env python
"""
assistant.py

Enhanced with web search for recipes and ingredient availability checks:
- Web Search (DuckDuckGo/Google Custom Search) for recipes
- MongoDB for ingredient availability only
- No recipe database needed
"""

import os
import json
import asyncio
import requests
from typing import List, Dict, Tuple, Set
from dotenv import load_dotenv
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient
from difflib import get_close_matches
import re

# Load env vars
load_dotenv("../.env")  # Load from parent directory (root) since script runs from backend/

# --- MongoDB Client ---
try:
    mongo_uri = os.getenv("MONGO_URI")
    mongo_db_name = os.getenv("MONGO_DB")
    
    if not mongo_uri:
        print("Warning: MONGO_URI not set, using default localhost")
        mongo_uri = "mongodb://localhost:27017"
    
    if not mongo_db_name:
        print("Warning: MONGO_DB not set, using default database")
        mongo_db_name = "restaurant_db"
    
    mongo_client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    # Test the connection
    mongo_client.admin.command('ping')
    db = mongo_client[mongo_db_name]
    # print(f"SUCCESS: MongoDB connected to {mongo_db_name}")  # Commented out to avoid showing in user response
    
except Exception as e:
    print(f"ERROR: MongoDB connection failed: {e}")
    print("Running in offline mode - some features may be limited")
    db = None
    mongo_client = None

# --- Ingredient Availability Check ---
def get_ingredient_availability() -> Dict[str, int]:
    """Get current ingredient availability from MongoDB"""
    if db is None:
        return {}
    
    try:
        collection = db["ingredients"]  # Your Ingredients collection
        inventory = {}
        for doc in collection.find({}):
            name = doc["name"].lower()
            current_stock = doc.get("currentStock", 0)
            inventory[name] = current_stock
        return inventory
    except Exception as e:
        print(f"Error loading ingredients: {e}")
        return {}

# --- Domain Guard ---
def is_restaurant_domain(text: str) -> bool:
    """Rudimentary domain guard: only allow restaurant-related topics"""
    text_lower = text.lower()
    domain_keywords = [
        # food/dishes
        "recipe", "ingredients", "cook", "prepare", "dish", "menu",
        "burger", "pizza", "pasta", "salad", "soup", "cake", "bread",
        "chicken", "beef", "pork", "fish", "rice", "fries", "sandwich",
        "omelet", "omelette", "mushroom", "mushrooms",
        # drinks
        "drink", "juice", "water", "soda", "coffee", "tea",
        # inventory/ops
        "inventory", "stock", "available", "availability", "in stock",
        "order", "orders", "kitchen", "ingredient", "items",
        # common supplies mentioned by staff
        "oil", "olive", "olive oil", "cheese", "mushroom", "mushrooms",
        "cans", "buckets", "salt", "pepper"
    ]
    return any(word in text_lower for word in domain_keywords)

# --- Intent Classification ---
def classify_intent(text: str) -> str:
    """Classify user intent from text"""
    text_lower = text.lower()

    # Out-of-domain early exit
    if not is_restaurant_domain(text_lower):
        return "out_of_domain"

    # Recipe/How-to queries (include singular/plural ingredient patterns)
    if re.search(r"\b(recipe|how to (make|cook|prepare)|how do i (make|cook|prepare)|ingredients?\s+(of|for)|give me the ingredients?\s+(of|for))\b", text_lower):
        return "recipe_request"

    # Inventory queries
    if re.search(r"\b(stock|inventory|available|availability|have|need|how many|do we have|in stock|left|quantity|count|units?)\b", text_lower):
        return "inventory_check"

    # Trending/recommendations
    if re.search(r"\b(trending|popular|recommend|suggestion)\b", text_lower):
        return "trending_request"

    return "general_query"

def extract_dish_name(text: str) -> str:
    """Extract dish name from user text"""
    text_lower = text.lower()
    
    # Look for patterns like "how to make X", "recipe for X", etc.
    patterns = [
        r"how to (?:make|cook|prepare)\s+([a-zA-Z\s]+)",
        r"recipe for\s+([a-zA-Z\s]+)",
        r"ingredients of\s+([a-zA-Z\s]+)",
        r"ingredient of\s+([a-zA-Z\s]+)",
        r"how to\s+([a-zA-Z\s]+)",
        r"([a-zA-Z\s]+)\s+recipe",
        r"ingredients for\s+([a-zA-Z\s]+)"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            dish_name = match.group(1).strip()
            # remove trailing politeness or filler words
            dish_name = re.sub(r"\b(please|thanks|thank you|ask)\b$", "", dish_name).strip()
            if dish_name and len(dish_name) > 1:
                return dish_name
    
    # If no pattern match, try to extract from common food words
    food_words = ["lemon juice", "pizza", "pasta", "salad", "soup", "cake", "bread", "rice", "chicken", "fish", "beef", "pork", "burger", "mushroom salad"]
    for food in food_words:
        if food in text_lower:
            return food
    
    return None

def find_closest_ingredient(name: str, inventory_keys: List[str]) -> str:
    """Find closest ingredient name in inventory"""
    if not inventory_keys:
        return name
    matches = get_close_matches(name, inventory_keys, n=1, cutoff=0.6)
    return matches[0] if matches else name

def check_inventory_availability(dish: str, inventory: Dict[str, int]) -> str:
    """Check ingredient availability for a dish using common ingredient lists"""
    if not inventory:
        return "The inventory is currently empty."
    return check_inventory_for_any_dish(dish, inventory)

def get_trending_recipes() -> str:
    """Get trending recipes based on recent queries"""
    if db is None:
        return "Trending data not available."
    
    try:
        trending = get_recent_trending(3)
        if trending:
            return f"Recent trending dishes: {', '.join(trending)}"
        else:
            return "No trending data available yet."
    except Exception as e:
        return "Unable to fetch trending data."

def log_query(user_text: str, dish_name: str):
    """Log user queries for analytics"""
    if db is not None:
        try:
            db["query_logs"].insert_one({
                "user_query": user_text,
                "dish_mentioned": dish_name,
                "timestamp": datetime.now(timezone.utc)
            })
        except Exception as e:
            print(f"Failed to log query: {e}")

def get_recent_trending(days=3):
    """Get recent trending dishes"""
    if db is None:
        return []
    
    try:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        pipeline = [
            {"$match": {"timestamp": {"$gte": since}}},
            {"$group": {"_id": "$dish_mentioned", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}, {"$limit": 3}
        ]
        return [f"{r['_id']} ({r['count']} requests)" for r in db["query_logs"].aggregate(pipeline)]
    except Exception as e:
        print(f"Error getting trending: {e}")
        return []

# --- Web Search Fallback (Replaced Bing with DuckDuckGo and Google Custom Search) ---
def duckduckgo_search(query: str) -> str:
    """Free search using DuckDuckGo Instant Answer API"""
    try:
        url = "https://api.duckduckgo.com/"
        params = {
            "q": f"{query} recipe ingredients instructions how to make step by step cooking method preparation",
            "format": "json",
            "no_html": "1",
            "skip_disambig": "1"
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Extract relevant information
        if data.get("Abstract"):
            abstract = data["Abstract"]
            # Clean up the abstract
            abstract = re.sub(r'\s+', ' ', abstract).strip()
            if len(abstract) > 20:  # Lowered threshold to get more results
                return abstract
        
        # Try to get related topics
        if data.get("RelatedTopics") and len(data["RelatedTopics"]) > 0:
            for topic in data["RelatedTopics"][:8]:  # Check more topics
                if isinstance(topic, dict) and "Text" in topic:
                    text = topic["Text"]
                    text = re.sub(r'\s+', ' ', text).strip()
                    # More flexible matching for recipe content
                    if len(text) > 20 and any(keyword in text.lower() for keyword in ["recipe", "ingredient", "how to", "cook", "prepare", "make", "step", "method"]):
                        return text
        
        return None
        
    except Exception as e:
        print(f"DuckDuckGo search failed: {e}")
        return None

# Google Custom Search removed - using only DuckDuckGo for simplicity

def web_search(query: str) -> str:
    """Web search using DuckDuckGo Instant Answer API"""
    
    print(f"Starting DuckDuckGo search for: {query}")  # Debug log
    
    # Use DuckDuckGo (free, no API key required)
    duckduckgo_result = duckduckgo_search(query)
    if duckduckgo_result:
        print(f"DuckDuckGo search successful for: {query}")  # Debug log
        return duckduckgo_result
    
    print(f"DuckDuckGo search failed for: {query}")  # Debug log
    return None

def get_basic_recipe(dish: str) -> str:
    """Provide basic recipe information when web search fails"""
    dish_lower = dish.lower()
    
    basic_recipes = {
        "burger": """Classic Burger Recipe:
1. Mix 1 lb ground beef with 1 tsp salt, 1/2 tsp pepper, 1/2 tsp garlic powder
2. Form into 4 equal patties, make thumb indentation in center
3. Heat oil in pan/grill to medium-high heat
4. Cook patties 4-5 minutes per side for medium-rare
5. Add cheese in last minute if desired
6. Toast buns, assemble with lettuce, tomato, onion, pickles
7. Serve with ketchup, mustard, and mayo""",
        
        "pizza": """Pizza Recipe:
1. Make dough: Mix 3 cups flour, 1 tsp yeast, 1 cup warm water, 1 tsp salt, 1 tbsp olive oil
2. Knead for 10 minutes, let rise 1 hour
3. Roll out dough, add tomato sauce, cheese, and toppings
4. Bake at 450°F (230°C) for 12-15 minutes until golden""",
        
        "omelet": """Classic Egg Omelet Recipe:
1. Beat 3 eggs with 1 tbsp water, salt and pepper to taste
2. Heat 1 tbsp butter in non-stick pan over medium heat
3. Pour in beaten eggs, let set for 30 seconds
4. Add fillings (cheese, vegetables, meat) to one half
5. Fold other half over, cook 1-2 minutes until set
6. Slide onto plate and serve immediately""",
        
        "egg omelet": """Classic Egg Omelet Recipe:
1. Beat 3 eggs with 1 tbsp water, salt and pepper to taste
2. Heat 1 tbsp butter in non-stick pan over medium heat
3. Pour in beaten eggs, let set for 30 seconds
4. Add fillings (cheese, vegetables, meat) to one half
5. Fold other half over, cook 1-2 minutes until set
6. Slide onto plate and serve immediately""",
        
        "lemon juice": """Lemon Juice Recipe:
1. Wash and roll 4-6 fresh lemons on counter to release juice
2. Cut lemons in half and juice using citrus juicer or by hand
3. Strain through fine mesh to remove seeds and pulp
4. Mix with water and sugar to taste (typically 1:1 ratio)
5. Serve over ice""",
        
        "pasta": """Basic Pasta Recipe:
1. Boil 1 lb pasta in salted water until al dente (8-10 minutes)
2. Drain, reserving 1 cup pasta water
3. Toss with olive oil, garlic, salt, and pepper
4. Add pasta water if needed for creaminess
5. Top with grated cheese and fresh herbs""",
        
        "cake": """Basic Cake Recipe:
1. Mix 2 cups flour, 1 cup sugar, 1 tsp baking powder, 1/2 tsp salt
2. Beat in 2 eggs, 1/2 cup milk, 1/3 cup oil
3. Pour into greased 9x9 pan
4. Bake at 350°F (175°C) for 25-30 minutes
5. Cool before frosting""",
        
        "bread": """Basic Bread Recipe:
1. Mix 3 cups flour, 1 tsp yeast, 1 tsp salt, 1 tbsp sugar
2. Add 1 cup warm water, knead for 10 minutes
3. Let rise 1 hour, punch down, shape
4. Rise again 30 minutes, bake at 400°F (200°C) for 30 minutes""",
        
        "mushroom salad": """Simple Mushroom Salad Recipe:
1. Clean and slice 8 oz fresh mushrooms
2. Mix with 2 tbsp olive oil, 1 tbsp lemon juice, salt and pepper
3. Add 1/4 cup chopped parsley and 2 tbsp grated parmesan
4. Let marinate 15 minutes, serve chilled"""
    }
    
    # Find best match
    for key, recipe in basic_recipes.items():
        if key in dish_lower:
            return recipe
    
    # Generic recipe for unknown dishes
    return f"""Basic Cooking Tips for {dish}:
1. Start with fresh, quality ingredients
2. Follow proper food safety practices
3. Season to taste with salt and pepper
4. Cook at appropriate temperatures
5. Let food rest before serving
6. Taste as you cook and adjust seasoning"""

def check_inventory_for_any_dish(dish: str, inventory: Dict[str, int]) -> str:
    """Check ingredient availability for any dish (not just database recipes)"""
    if not inventory:
        return f"You don't have the ingredients needed for {dish}. The inventory is currently empty."
    
    # Common ingredients for different dish types
    common_ingredients = {
        "burger": [
            "bun", "buns", "beef", "beef patty", "patty", "cheese", "lettuce",
            "tomato", "onion", "pickles", "ketchup", "mustard", "mayo",
            "oil", "salt", "pepper"
        ],
        "omelet": ["eggs", "butter", "salt", "pepper", "water", "cheese", "vegetables"],
        "egg omelet": ["eggs", "butter", "salt", "pepper", "water", "cheese", "vegetables"],
        "mushroom salad": ["mushrooms", "olive oil", "lemon juice", "salt", "pepper", "parsley", "parmesan"],
        "pizza": ["flour", "yeast", "water", "salt", "olive oil", "tomato", "cheese", "basil"],
        "lemon juice": ["lemon", "water", "sugar", "salt"],
        "pasta": ["flour", "eggs", "salt", "olive oil", "tomato", "cheese"],
        "salad": ["lettuce", "tomato", "cucumber", "olive oil", "vinegar", "salt"],
        "soup": ["vegetables", "broth", "salt", "pepper", "herbs"],
        "cake": ["flour", "sugar", "eggs", "milk", "butter", "baking powder"],
        "bread": ["flour", "yeast", "water", "salt", "sugar"],
        "rice": ["rice", "water", "salt", "butter"],
        "chicken": ["chicken", "oil", "salt", "pepper", "herbs"],
        "fish": ["fish", "oil", "salt", "pepper", "lemon"],
        "beef": ["beef", "oil", "salt", "pepper", "garlic"],
        "pork": ["pork", "oil", "salt", "pepper", "garlic"]
    }
    
    # Find the best matching dish category
    best_match = None
    best_score = 0
    
    for dish_type, ingredients in common_ingredients.items():
        if dish_type in dish.lower():
            best_match = dish_type
            break
        # Check for partial matches
        score = sum(1 for word in dish.lower().split() if word in dish_type)
        if score > best_score:
            best_score = score
            best_match = dish_type
    
    if not best_match:
        # Generic ingredients for unknown dishes
        generic_ingredients = ["flour", "salt", "oil", "water", "eggs", "milk", "sugar", "herbs"]
        return analyze_ingredients(generic_ingredients, inventory, dish)
    
    # Check ingredients for the specific dish
    return analyze_ingredients(common_ingredients[best_match], inventory, dish)

def analyze_ingredients(required_ingredients: List[str], inventory: Dict[str, int], dish: str) -> str:
    """Analyze ingredient availability and provide detailed feedback"""
    if not inventory:
        return f"You don't have the ingredients needed for {dish}. The inventory is currently empty."
    
    available = []
    missing = []
    low_stock = []
    
    for ingredient in required_ingredients:
        # Find closest match in inventory
        closest = find_closest_ingredient(ingredient, list(inventory.keys()))
        if closest in inventory:
            stock = inventory[closest]
            if stock > 0:
                available.append(f"{closest} ({stock})")
                if stock <= 2:  # Consider low stock if 2 or less
                    low_stock.append(closest)
            else:
                missing.append(ingredient)
        else:
            missing.append(ingredient)
    
    # Build response
    response_parts = []
    
    if available:
        response_parts.append(f"Available: {', '.join(available)}")
    
    if low_stock:
        response_parts.append(f"Low stock: {', '.join(low_stock)}")
    
    if missing:
        if len(missing) == 1:
            response_parts.append(f"You miss ingredient: {missing[0]}")
        else:
            response_parts.append(f"You miss ingredients: {', '.join(missing)}")
    
    if not response_parts:
        response_parts.append("No ingredient information available.")
    
    return " | ".join(response_parts)


def _generate_ngrams(tokens: List[str], n: int = 2) -> Set[str]:
    ngrams: Set[str] = set()
    for i in range(len(tokens) - n + 1):
        ngrams.add(" ".join(tokens[i : i + n]))
    return ngrams


def analyze_inventory_query(user_text: str, inventory: Dict[str, int]) -> str:
    """Answer direct inventory questions for specific items mentioned in the text."""
    if db is not None and not inventory:
        # DB connected but no items present
        return "The inventory is currently empty."

    if not inventory:
        return "No inventory data available."

    text_lower = user_text.lower()
    tokens = re.findall(r"[a-zA-Z]+", text_lower)
    tokens = [t for t in tokens if t not in {"how", "to", "make", "cook", "prepare", "the", "a", "an", "and", "of", "for", "do", "we", "have", "any", "is", "there", "stock", "in", "our", "restaurant", "available", "availability", "left", "many", "quantity", "count", "units", "unit", "give", "me"}]

    bigrams = _generate_ngrams(tokens, 2)
    candidate_terms: Set[str] = set(tokens) | bigrams

    inventory_keys = list(inventory.keys())
    matched: List[Tuple[str, int]] = []

    # Direct substring matches first
    for key in inventory_keys:
        if key in text_lower:
            matched.append((key, inventory[key]))

    # Fuzzy match for remaining
    matched_keys = {k for k, _ in matched}
    for term in candidate_terms:
        if any(term in k or k in term for k in matched_keys):
            continue
        close = get_close_matches(term, inventory_keys, n=1, cutoff=0.82)
        if close:
            key = close[0]
            if key not in matched_keys:
                matched.append((key, inventory[key]))
                matched_keys.add(key)

    if not matched:
        # Provide a helpful hint if no terms matched
        sample = ", ".join(list(inventory.keys())[:5]) if inventory else ""
        hint = f" Known inventory items include: {sample}." if sample else ""
        return "I couldn't find those items in the inventory." + hint

    # Build concise response
    parts = [f"{name}: {qty}" for name, qty in matched]
    return " | ".join(parts)

async def get_recipe_with_fallback(dish: str, user_text: str, inventory: Dict[str, int]):
    """Get recipe with web search fallback"""
    
    # Always search web first for recipes (prioritize web search for all dishes)
    print(f"Searching web for recipe: {dish}")  # Debug log
    web_result = web_search(dish)
    
    if web_result:
        print(f"Web search successful for {dish}")  # Debug log
        # Check ingredient availability
        availability_info = check_inventory_for_any_dish(dish, inventory)
        return f"{web_result}\n\n{availability_info}"
    
    print(f"Web search failed for {dish}, using fallback recipe")  # Debug log
    # If web search fails, provide basic cooking tips
    fallback_help = get_basic_recipe(dish)
    availability_info = check_inventory_for_any_dish(dish, inventory)
    return f"{fallback_help}\n\n{availability_info}"

# --- Main Logic ---
async def restaurant_agent(user_text: str, inventory: Dict[str, int], is_audio: bool = False):
    """Main restaurant agent function"""
    
    intent = classify_intent(user_text)
    dish = extract_dish_name(user_text)
    
    # Domain guard response
    if intent == "out_of_domain":
        return "I can only answer restaurant topics such as recipes, ingredients, menu items, and inventory."

    if intent == "recipe_request":
        if dish:
            log_query(user_text, dish)
            return await get_recipe_with_fallback(dish, user_text, inventory)
        else:
            return "I'd be happy to help you with a recipe! Could you please specify what dish you'd like to make? For example: 'How to make lemon juice' or 'Recipe for pizza'."
    
    elif intent == "inventory_check":
        # First, try to answer about specific items in the inventory mentioned in the query
        item_response = analyze_inventory_query(user_text, inventory)
        # If we found concrete items, return that; otherwise, if a dish is specified, analyze dish ingredients
        if item_response and not item_response.startswith("I couldn't find"):
            return item_response
        if dish:
            return check_inventory_availability(dish, inventory)
        # Fallback prompt
        if db is not None and not inventory:
            return "The inventory is currently empty."
        return "Tell me which items or dish you want me to check in the inventory."
    
    elif intent == "trending_request":
        return get_trending_recipes()
    
    elif intent == "general_query":
        return "I can help you with recipes, ingredient checks, and restaurant insights. What would you like to know?"
    
    # Default response
    return "I'm here to help with recipes and ingredient information. How can I assist you today?"

async def assistant_query(input_data: str, inventory: Dict[str, int], is_audio=False):
    """Main entry point for assistant queries"""
    try:
        result = await restaurant_agent(input_data, inventory, is_audio)
        return result
    except Exception as e:
        print(f"Error in assistant_query: {e}")
        return f"I encountered an error while processing your request: {str(e)}"

# --- Entry Point ---
if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Restaurant AI Assistant")
    parser.add_argument("text", help="User query text")
    parser.add_argument("--audio", help="Audio file path")
    args = parser.parse_args()
    
    # Get inventory from MongoDB
    inventory = get_ingredient_availability()
    
    # Process the query
    result = asyncio.run(assistant_query(args.text, inventory, is_audio=args.audio))
    print(result)
import os
import json
import random
import time
import threading
import datetime
import hashlib
import requests
from flask import Flask, jsonify, request, session, render_template

# ==========================================
# CONFIGURATION & DATA
# ==========================================

# !!! IMPORTANT !!!
# PASTE YOUR FIREBASE REALTIME DATABASE URL HERE
FIREBASE_DB_URL = "https://bonecraftsim-default-rtdb.firebaseio.com/" 
# -----------------

# Flask Setup
app = Flask(__name__)
# Set a secret key for session management (CHANGE THIS!)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "a_very_secret_key_for_bonecraft_sim")

app.config['SESSION_COOKIE_SECURE'] = True        # Must be True for production/HTTPS
app.config['SESSION_COOKIE_SAMESITE'] = 'None'    # Allows cookies to be sent cross-site (required for iFrames)
app.config['SESSION_COOKIE_DOMAIN'] = None

# Comprehensive Bonecraft recipes (Same as original)
BONECRAFT_RECIPES = [
    # Tier 5 (Amateur - Skill 1-10)
    {"name": "Bone Hairpin", "price": 100, "tier": 5, "material": "Bone Chip", "qty": 1},
    {"name": "Shell Ring", "price": 200, "tier": 5, "material": "Seashell", "qty": 1},
    
    # Tier 4 (Recruit - Skill 11-20)
    {"name": "Gelatin", "price": 300, "tier": 4, "material": "Chicken Bone", "qty": 2},
    {"name": "Bone Ring", "price": 450, "tier": 4, "material": "Sheep Tooth", "qty": 1},
    {"name": "Bone Mask", "price": 600, "tier": 4, "material": "Giant Femur", "qty": 1},
    {"name": "Carapace Powder", "price": 800, "tier": 4, "material": "Beetle Shell", "qty": 2},
    
    # Tier 3 (Initiate/Novice - Skill 21-40)
    {"name": "Beetle Ring", "price": 1200, "tier": 3, "material": "Beetle Jaw", "qty": 1},
    {"name": "Beetle Earring", "price": 1500, "tier": 3, "material": "Beetle Jaw", "qty": 1},
    {"name": "Horn Ring", "price": 2500, "tier": 3, "material": "Ram Horn", "qty": 1},
    {"name": "Turtle Shield", "price": 5000, "tier": 3, "material": "Turtle Shell", "qty": 1},
    
    # Tier 2 (Apprentice/Journeyman - Skill 41-60)
    {"name": "Carapace Helm", "price": 8500, "tier": 2, "material": "Turtle Shell", "qty": 2},
    {"name": "Scorpion Ring", "price": 15000, "tier": 2, "material": "Scorpion Shell", "qty": 1},
    
    # Tier 1 (Craftsman/Artisan - Skill 61-80)
    {"name": "Demon's Ring", "price": 30000, "tier": 1, "material": "Demon Horn", "qty": 1},
    {"name": "Tigerfang", "price": 45000, "tier": 1, "material": "Black Tiger Fang", "qty": 2},
    {"name": "Coral Gorget", "price": 60000, "tier": 1, "material": "Coral Fragment", "qty": 3},

    # Tier 0 (Adept/Veteran - Skill 81-100+)
    {"name": "Dragon Mask", "price": 120000, "tier": 0, "material": "Wyvern Scales", "qty": 2},
    {"name": "Trumpet Ring", "price": 500000, "tier": 0, "material": "Titanictus Shell", "qty": 1},
    {"name": "Chronos Tooth", "price": 800000, "tier": 0, "material": "Titanictus Shell", "qty": 1},
    {"name": "Gavial Mask", "price": 1000000, "tier": 0, "material": "Gavial Fish", "qty": 1},
]

# All primary materials used in the recipes, available for bot listing/purchase
BOT_LISTABLE_ITEMS = [
    "Bone Chip", "Seashell", "Chicken Bone", "Sheep Tooth", "Giant Femur", 
    "Beetle Shell", "Beetle Jaw", "Ram Horn", "Turtle Shell", "Scorpion Shell", 
    "Demon Horn", "Black Tiger Fang", "Coral Fragment", "Wyvern Scales", 
    "Titanictus Shell", "Gavial Fish"
]

BOT_NAMES = ["SephirothXX", "VanaFan99", "CrafterMain", "GilBuyer", "ChocoRacer"]


# ==========================================
# CLOUD AUTHENTICATION & DATABASE ENGINE
# (Integrated into Flask, uses direct Firebase calls)
# ==========================================

class CloudAuthServer:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip('/')

    def hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()

    def register(self, username, password):
        check_url = f"{self.base_url}/users/{username}.json"
        try:
            resp = requests.get(check_url)
            if resp.json() is not None:
                return False, "Username already taken."
        except Exception:
            return False, "Connection failed."
        
        user_profile = {
            "password": self.hash_password(password),
            "data": {
                "gil": 5000,
                "total_synths": 0,
                "inventory": {"Bone Chip": 20, "Seashell": 10, "Chicken Bone": 5, "Sheep Tooth": 5}, 
                "last_active": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        }
        
        try:
            requests.put(check_url, json=user_profile)
            return True, "Account created! Login to play."
        except Exception as e:
            return False, f"Cloud Error: {e}"

    def login(self, username, password):
        url = f"{self.base_url}/users/{username}.json"
        try:
            resp = requests.get(url)
            user_data = resp.json()
            
            if not user_data:
                return False, None, "User not found."
            
            stored_hash = user_data.get("password")
            if stored_hash == self.hash_password(password):
                return True, user_data.get("data"), "Login successful."
            else:
                return False, None, "Invalid password."
        except Exception:
            return False, None, "Network error during login."

    def sync_user_data(self, username, data):
        url = f"{self.base_url}/users/{username}/data.json"
        data['last_active'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            requests.patch(url, json=data)
            return True
        except Exception as e:
            print(f"Failed to sync: {e}")
            return False
            
    # --- AH Methods ---
    def list_item_to_cloud(self, item_name, price, seller_name, qty=1):
        url = f"{self.base_url}/auction_house.json"
        listing = {
            "item": item_name,
            "price": price, 
            "seller": seller_name,
            "qty": qty, 
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        try:
            resp = requests.post(url, json=listing)
            return resp.json().get('name'), listing
        except Exception as e:
            print(f"Cloud List Error: {e}")
            return None, None

    def buy_item_from_cloud(self, listing_id, buyer_name):
        listing_url = f"{self.base_url}/auction_house/{listing_id}.json"
        try:
            resp = requests.get(listing_url)
            listing = resp.json()

            if not listing:
                return False, "Item already sold.", None

            # 2. Delete the item from the auction house
            requests.delete(listing_url)

            # 3. Update the seller's Gil (unless it's a bot)
            if listing['seller'] != buyer_name and listing['seller'] not in BOT_NAMES:
                seller_url = f"{self.base_url}/users/{listing['seller']}/data/gil.json"
                
                gil_resp = requests.get(seller_url)
                seller_gil = gil_resp.json() or 0
                new_gil = seller_gil + listing['price']
                
                requests.put(seller_url, json=new_gil)
            
            return True, "Purchase successful.", listing

        except Exception as e:
            print(f"Cloud Buy Error: {e}")
            return False, "Network error during purchase.", None
            
    def fetch_market_data(self):
        url = f"{self.base_url}/auction_house.json"
        try:
            resp = requests.get(url)
            listings_dict = resp.json() or {}
            
            listings_list = []
            for listing_id, listing_data in listings_dict.items():
                listing_data['id'] = listing_id
                listing_data['qty'] = listing_data.get('qty', 1) 
                listings_list.append(listing_data)
            
            listings_list.sort(key=lambda x: x['time'], reverse=True)
            
            return listings_list
        except Exception as e:
            print(f"Market fetch error: {e}")
            return []

    def fetch_leaderboard(self):
        url = f"{self.base_url}/users.json"
        try:
            resp = requests.get(url)
            all_users = resp.json()
            if not all_users: return []
            
            leaderboard = []
            for name, profile in all_users.items():
                if "data" in profile and name not in BOT_NAMES:
                    d = profile["data"]
                    leaderboard.append({
                        "name": name,
                        "gil": d.get("gil", 0),
                        "synths": d.get("total_synths", 0)
                    })
            return leaderboard
        except Exception:
            return []

# ==========================================
# HELPER CLASSES (Simplified for Web Context)
# ==========================================

class Player:
    def __init__(self, name, data):
        self.name = name
        self.gil = data.get("gil", 5000)
        self.inventory = data.get("inventory") or {}
        self.total_synths = data.get("total_synths", 0)

    def to_dict(self):
        return {
            "gil": self.gil,
            "inventory": self.inventory,
            "total_synths": self.total_synths
        }

    def add_item(self, item_name, qty=1):
        self.inventory[item_name] = self.inventory.get(item_name, 0) + qty

    def remove_item(self, item_name, qty=1):
        if self.inventory.get(item_name, 0) >= qty:
            self.inventory[item_name] -= qty
            if self.inventory[item_name] <= 0:
                del self.inventory[item_name]
            return True
        return False
        
# Initialize the Auth Server globally
auth_server = CloudAuthServer(FIREBASE_DB_URL)

# ==========================================
# FLASK ROUTES
# ==========================================

@app.route('/')
def serve_index():
    # Serve the HTML frontend
    return render_template('index.html')

def get_player_data():
    """Helper to fetch and return the Player object from the database"""
    if 'username' not in session:
        return None
    username = session['username']
    
    url = f"{auth_server.base_url}/users/{username}/data.json"
    try:
        resp = requests.get(url)
        data = resp.json()
        if data:
            return Player(username, data)
        else:
            session.pop('username', None) # Log out if data is gone
            return None
    except Exception:
        return None

# --- Auth Routes ---

@app.route('/api/auth/register', methods=['POST'])
def api_register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"success": False, "message": "Missing username or password"}), 400
        
    success, message = auth_server.register(username, password)
    return jsonify({"success": success, "message": message})

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"success": False, "message": "Missing username or password"}), 400
        
    success, user_data, message = auth_server.login(username, password)
    if success:
        session['username'] = username
        return jsonify({"success": True, "message": message, "username": username})
    else:
        return jsonify({"success": False, "message": message}), 401

@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    session.pop('username', None)
    return jsonify({"success": True})


# --- Game API Routes ---

@app.route('/api/game/sync', methods=['GET'])
def api_sync():
    player = get_player_data()
    if not player:
        return jsonify({"success": False, "message": "Not authenticated"}), 401
        
    return jsonify({
        "success": True, 
        "player": player.to_dict(),
        "recipes": BONECRAFT_RECIPES
    })

@app.route('/api/game/synth', methods=['POST'])
def api_synth():
    player = get_player_data()
    if not player:
        return jsonify({"success": False, "message": "Not authenticated"}), 401
        
    data = request.get_json()
    recipe_name = data.get('recipe_name')
    
    recipe = next((r for r in BONECRAFT_RECIPES if r["name"] == recipe_name), None)
    if not recipe:
        return jsonify({"success": False, "message": "Invalid recipe"}), 400
        
    cost = int(recipe["price"] * 0.1) 
    material_name = recipe["material"]
    material_qty = recipe["qty"]

    if player.gil < cost:
        return jsonify({"success": False, "message": "Not enough Gil for synthesis fee!"})
    
    if player.inventory.get(material_name, 0) < material_qty:
        return jsonify({"success": False, "message": f"Missing material: {material_qty}x {material_name}!"})

    # Perform Transaction
    player.gil -= cost
    player.total_synths += 1
    
    roll = random.randint(1, 100)
    tier = recipe["tier"]
    result = "NQ"
    
    if tier == 5: result = "BREAK" if roll <= 10 else ("HQ" if roll > 40 else "NQ")
    elif tier == 4: result = "BREAK" if roll <= 15 else ("HQ" if roll > 50 else "NQ")
    elif tier == 3: result = "BREAK" if roll <= 20 else ("HQ" if roll > 60 else "NQ")
    elif tier == 2: result = "BREAK" if roll <= 25 else ("HQ" if roll > 70 else "NQ")
    elif tier == 1: result = "BREAK" if roll <= 30 else ("HQ" if roll > 80 else "NQ")
    else: result = "BREAK" if roll <= 35 else ("HQ" if roll > 90 else "NQ")

    synth_message = ""
    if result == "BREAK":
        player.remove_item(material_name, material_qty)
        synth_message = f"Synthesis Failed! Materials lost. (Roll: {roll})"
    else:
        player.remove_item(material_name, material_qty)
        
        item_name = recipe["name"]
        if result == "HQ":
            item_name = f"HQ {item_name} (+1)"
            synth_message = f"High Quality!! Got {item_name}"
        else:
            synth_message = f"Success. Got {item_name}"
        player.add_item(item_name)

    # Save state back to cloud
    auth_server.sync_user_data(player.name, player.to_dict())
    
    return jsonify({
        "success": True,
        "message": synth_message,
        "result": result,
        "player": player.to_dict()
    })

@app.route('/api/ah/market', methods=['GET'])
def api_market():
    listings = auth_server.fetch_market_data()
    return jsonify({"success": True, "listings": listings})

@app.route('/api/ah/list', methods=['POST'])
def api_list_item():
    player = get_player_data()
    if not player:
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    data = request.get_json()
    item_name = data.get('item')
    price = data.get('price')
    qty = data.get('qty')

    if not all([item_name, price, qty]) or price <= 0 or qty <= 0:
        return jsonify({"success": False, "message": "Invalid listing details."}), 400
    
    if player.inventory.get(item_name, 0) < qty:
        return jsonify({"success": False, "message": "You don't have enough of this item."}), 400
    
    # Remove from local inventory
    player.remove_item(item_name, qty)
    
    # List to cloud
    listing_id, listing_data = auth_server.list_item_to_cloud(item_name, price, player.name, qty)
    
    if listing_id:
        # Save updated inventory to cloud
        auth_server.sync_user_data(player.name, player.to_dict())
        return jsonify({"success": True, "message": f"Listed {qty}x {item_name} for {price:,}g."})
    else:
        # Refund item if cloud list fails
        player.add_item(item_name, qty)
        return jsonify({"success": False, "message": "Failed to list item to cloud."}), 500

@app.route('/api/ah/buy', methods=['POST'])
def api_buy_item():
    player = get_player_data()
    if not player:
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    
    data = request.get_json()
    listing_id = data.get('listing_id')

    # 1. Attempt to buy from cloud (atomic transaction)
    success, msg, purchased_data = auth_server.buy_item_from_cloud(listing_id, player.name)

    if success:
        total_price = purchased_data['price']
        qty = purchased_data.get('qty', 1)
        item_name = purchased_data['item']
        
        if player.gil < total_price:
             # The item was bought from AH but user can't afford it. 
             # In a real game, this shouldn't happen, but for simplicity: refund the AH.
             # Here, we assume the frontend checked affordability first.
             # We just prevent the local player from getting the item/losing Gil.
             auth_server.list_item_to_cloud(item_name, total_price, purchased_data['seller'], qty) # Re-list item
             return jsonify({"success": False, "message": "Transaction failed: Insufficient Gil."}), 400
        
        # 2. Update local player state
        player.gil -= total_price
        player.add_item(item_name, qty)
        
        # 3. Save state back to cloud
        auth_server.sync_user_data(player.name, player.to_dict())
        
        return jsonify({
            "success": True,
            "message": f"Bought {qty}x {item_name} for {total_price:,}g.",
            "player": player.to_dict()
        })
    else:
        return jsonify({"success": False, "message": msg}), 400

@app.route('/api/game/leaderboard', methods=['GET'])
def api_leaderboard():
    leaderboard_data = auth_server.fetch_leaderboard()
    leaderboard_data.sort(key=lambda x: x['gil'], reverse=True)
    return jsonify({"success": True, "leaderboard": leaderboard_data})


# ==========================================
# BACKGROUND ECONOMY SIMULATION
# ==========================================

def run_economy_simulation():
    """Runs in a separate thread to simulate bot activity."""
    print("--- Starting Economy Simulation Thread ---")
    while True:
        try:
            # Bots list materials (30% chance every cycle)
            if random.randint(1, 10000) <= 25:
                bot = random.choice(BOT_NAMES)
                item_to_list = random.choice(BOT_LISTABLE_ITEMS)
                
                list_qty = 1
                if random.random() < 0.5: list_qty = 12 
                elif random.random() < 0.25: list_qty = 6 

                # Determine base price (unit price)
                base_price = 100
                if item_to_list in ["Chicken Bone", "Sheep Tooth", "Giant Femur"]: base_price = 500
                elif item_to_list in ["Beetle Shell", "Beetle Jaw", "Ram Horn"]: base_price = 1500
                elif item_to_list in ["Turtle Shell", "Scorpion Shell"]: base_price = 3000
                elif item_to_list in ["Demon Horn", "Black Tiger Fang", "Coral Fragment"]: base_price = 8000
                elif item_to_list in ["Wyvern Scales", "Titanictus Shell", "Gavial Fish"]: base_price = 25000
                
                unit_price = int(base_price * random.uniform(0.8, 1.5))
                total_price = unit_price * list_qty
                
                auth_server.list_item_to_cloud(item_to_list, total_price, bot, qty=list_qty)
                
            # Bots buy items (20% chance every cycle)
            elif random.random() < 0.2:
                listings = auth_server.fetch_market_data()
                if listings:
                    target = random.choice(listings)
                    base_unit_price = 0
                    
                    # Estimate value for buy decision
                    for r in BONECRAFT_RECIPES:
                        if r['name'] in target['item']:
                            base_unit_price = r['price'] * (3 if 'HQ' in target['item'] else 1)
                            break
                    if not base_unit_price and target['item'] in BOT_LISTABLE_ITEMS:
                        # Use the same base price logic as listing
                        if target['item'] in ["Bone Chip", "Seashell"]: base_unit_price = 100
                        elif target['item'] in ["Chicken Bone", "Sheep Tooth", "Giant Femur"]: base_unit_price = 500
                        elif target['item'] in ["Beetle Shell", "Beetle Jaw", "Ram Horn"]: base_unit_price = 1500
                        elif target['item'] in ["Turtle Shell", "Scorpion Shell"]: base_unit_price = 3000
                        elif target['item'] in ["Demon Horn", "Black Tiger Fang", "Coral Fragment"]: base_unit_price = 8000
                        elif target['item'] in ["Wyvern Scales", "Titanictus Shell", "Gavial Fish"]: base_unit_price = 25000

                    listing_unit_price = target['price'] / target.get('qty', 1)
                        
                    # Simplified bot purchase logic: only buy if price is good (or 5% chance anyway)
                    if listing_unit_price < base_unit_price * 1.2 or random.random() < 0.05:
                        buyer = random.choice(BOT_NAMES)
                        auth_server.buy_item_from_cloud(target['id'], buyer)
            
        except Exception as e:
            print(f"Economy Error: {e}")
            
        time.sleep(random.uniform(3, 6)) # Wait 3-6 seconds before next tick

# Run the economy simulation in a daemon thread
threading.Thread(target=run_economy_simulation, daemon=True).start()

if __name__ == '__main__':
    # Use 0.0.0.0 for hosting on a public server
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
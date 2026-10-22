from flask import (
    Flask,
    redirect,
    request,
    render_template,
    session,
    send_from_directory,
    jsonify
)

from pymongo import MongoClient
from plyer import notification
from bson.objectid import ObjectId
from datetime import timedelta, datetime
from pywebpush import webpush, WebPushException
from dotenv import load_dotenv
from waste_prediction_model import predict_waste_risk

import threading
import time
import markdown
import os

from google import genai
from eat_first_model import predict_priority

load_dotenv()

# Configure GEMINI_API_KEY in .env locally and in Render Environment.
gemini_api_key = os.getenv("GEMINI_API_KEY")
genai_client = genai.Client(api_key=gemini_api_key) if gemini_api_key else None


def safe_notify(**kwargs):
    """Desktop notifications are only available on a local desktop."""
    if os.getenv("RENDER"):
        return
    try:
        notification.notify(**kwargs)
    except Exception as exc:
        app.logger.warning("Desktop notification unavailable: %s", exc)



# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY", "local-development-only-change-me")
app.permanent_session_lifetime = timedelta(days=15)


# =========================================================
# MONGODB
# =========================================================

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI is missing. Set it in .env or Render Environment.")

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)

db = client["food_manager"]

collection = db["collection"]

reg = db["register"]

# NEW: stores browser push subscriptions
push_subscriptions = db["push_subscriptions"]


DAYS_BEFORE_EXPIRY = 1


# =========================================================
# EXPIRY CHECK
# =========================================================

def check_expiry():

    while True:

        today = datetime.now().date()

        reminder_date = today + timedelta(
            days=DAYS_BEFORE_EXPIRY
        )

        foods = collection.find()

        for food in foods:

            expiry = datetime.strptime(
                food["expiry"],
                "%Y-%m-%d"
            ).date()

            if expiry == reminder_date:

                safe_notify(
                    title="Food Expiry Reminder",
                    message=f"{food['food_name']} will expire tomorrow!",
                    timeout=10
                )

        time.sleep(36000)

def get_prevention_tips(
    category,
    storage,
    days_left,
    risk
):

    tips = []


    if risk == "HIGH":

        tips.append(
            "Consume this food as soon as possible."
        )

        tips.append(
            "Prioritize this item over foods "
            "with a longer shelf life."
        )


    elif risk == "MEDIUM":

        tips.append(
            "Plan to consume this food soon."
        )

        tips.append(
            "Avoid purchasing excess quantity "
            "until the existing stock is used."
        )


    else:

        tips.append(
            "Continue monitoring this food."
        )


    # Category-specific suggestions

    if category.lower() == "vegetable":

        tips.append(
            "Use older vegetables first "
            "before newer stock."
        )


    elif category.lower() == "fruit":

        tips.append(
            "Separate damaged or overripe fruits "
            "from fresh fruits."
        )


    elif category.lower() == "dairy":

        tips.append(
            "Keep dairy products properly refrigerated."
        )


    elif category.lower() == "bakery":

        tips.append(
            "Store bakery products appropriately "
            "to maintain freshness."
        )


    # Storage suggestion

    if storage.lower() == "room temperature":

        tips.append(
            "Check whether this food requires "
            "refrigeration according to its storage needs."
        )


    # Expiry warning

    if days_left <= 1:

        tips.append(
            "Do not delay consumption because "
            "the expiry date is very close."
        )


    return tips
# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    return render_template("reg.html")


# =========================================================
# WEB HOME
# =========================================================

@app.route("/webhome")
def webhome():

    return render_template("web.html")


# =========================================================
# REGISTER
# =========================================================

@app.route("/register", methods=["POST", "GET"])
def register():

    if request.method == "POST":

        name = request.form["name"]

        email = request.form["email"]

        password = request.form["password"]

        reg.insert_one({
            "name": name,
            "email": email,
            "password": password
        })

        safe_notify(
            title="Grocery Food Manager",
            message="Register Successfully!"
        )

        return redirect("/loginn")

    return render_template("reg.html")


# =========================================================
# LOGIN PAGE
# =========================================================

@app.route("/loginn")
def login_page():

    return render_template("login.html")


# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["POST", "GET"])
def login():

    if request.method == "GET":

        return render_template("login.html")

    email = request.form["email"]

    password = request.form["password"]

    user = reg.find_one({
        "email": email,
        "password": password
    })

    if user:

        session.permanent = True

        session["user_id"] = str(user["_id"])

        session["user_name"] = user["name"]

        session["user_email"] = user["email"]

        return render_template("web.html")

    return "Invalid email or password"


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/loginn")


# =========================================================
# ACCOUNT
# =========================================================

@app.route("/account")
def account():

    if "user_id" not in session:

        return redirect("/loginn")

    user = reg.find_one({
        "_id": ObjectId(session["user_id"])
    })

    if not user:

        return "User not found"

    return render_template(
        "account.html",
        user=user
    )


# =========================================================
# ADD FOOD PAGE
# =========================================================

@app.route("/add")
def add_food():

    if "user_email" not in session:

        return redirect("/")

    return render_template("add.html")


# =========================================================
# ADD FOOD
# =========================================================

@app.route("/add", methods=["POST"])
def add():

    if "user_id" not in session:

        return redirect("/")

    food_name = request.form["food_name"]

    category = request.form["category"]

    quantity = request.form["quantity"]

    storage_location = request.form["storage_location"]

    expiry = request.form["expiry"]

    collection.insert_one({

        "food_name": food_name,

        "category": category,

        "quantity": quantity,

        "storage_location": storage_location,

        "expiry": expiry,

        "user_id": session["user_id"]

    })

    safe_notify(
        title="Grocery Food Manager",
        message=f"{food_name} Added Successfully!"
    )

    return redirect("/view")


# =========================================================
# VIEW FOOD
# =========================================================

@app.route("/view")
def view():

    if "user_id" not in session:

        return redirect("/")

    foods = collection.find({
        "user_id": session["user_id"]
    })

    return render_template(
        "view.html",
        foods=foods
    )


# =========================================================
# DELETE FOOD
# =========================================================

@app.route("/delete/<id>")
def delete(id):

    if "user_id" not in session:

        return redirect("/")

    collection.delete_one({

        "_id": ObjectId(id),

        "user_id": session["user_id"]

    })

    safe_notify(
        title="Grocery Food Manager",
        message="Food Deleted Successfully!"
    )

    return redirect("/view")


# =========================================================
# SEARCH FOOD
# =========================================================

@app.route("/search")
def search():

    if "user_id" not in session:

        return redirect("/")

    food_name = request.args.get(
        "fname",
        ""
    )

    foods = collection.find({

        "user_id": session["user_id"],

        "food_name": {
            "$regex": food_name,
            "$options": "i"
        }

    })

    return render_template(
        "view.html",
        foods=foods
    )


# =========================================================
# ADMIN / ACCOUNTS
# =========================================================

@app.route("/accd")
def accd():

    acc = reg.find()

    return render_template(
        "accd.html",
        acc=acc
    )


# =========================================================
# DELETE USER
# =========================================================

@app.route("/delete_user/<u_id>")
def delete_user(u_id):

    reg.delete_one({
        "_id": ObjectId(u_id)
    })

    safe_notify(
        title="Grocery Food Manager",
        message="Account Deleted Successfully!"
    )

    return redirect("/register")


# =========================================================
# AI RECIPE PAGE
# =========================================================

@app.route("/f")
def f():

    return render_template("index.html")


# =========================================================
# AI RECIPE GENERATOR
# =========================================================

@app.route("/food", methods=["POST"])
def food():

    if request.method == "POST":

        foodname = request.form["foodname"]

        if genai_client is None:
            return "GEMINI_API_KEY is not configured on the server.", 503

        response = genai_client.models.generate_content(

            model="gemini-3.8-flash",

            contents=f"""
food name: {foodname}

Suggest exactly 3 recipes using this food.

For each recipe, use this exact Markdown structure:

## Recipe 1: Recipe Name

### Ingredients
- Ingredient 1
- Ingredient 2
- Ingredient 3
- Ingredient 4

### Steps
1. Step one
2. Step two
3. Step three
4. Step four

## Recipe 2: Recipe Name

### Ingredients
- Ingredient 1
- Ingredient 2
- Ingredient 3

### Steps
1. Step one
2. Step two
3. Step three

## Recipe 3: Recipe Name

### Ingredients
- Ingredient 1
- Ingredient 2
- Ingredient 3

### Steps
1. Step one
2. Step two
3. Step three

Keep the recipes concise.
Return ONLY Markdown. Do not use HTML.
"""
        )

        result = markdown.markdown(
            response.text
        )

    return render_template(
        "index.html",
        foodname=foodname,
        result=result
    )


# =========================================================
# SERVICE WORKER
# =========================================================

@app.route("/sw.js")
def service_worker():

    return send_from_directory(
        "static",
        "sw.js",
        mimetype="application/javascript"
    )


# =========================================================
# SAVE PUSH SUBSCRIPTION
# =========================================================

@app.route("/save-subscription", methods=["POST"])
def save_subscription():

    # User must be logged in
    if "user_id" not in session:

        return jsonify({
            "success": False,
            "message": "User not logged in"
        }), 401

    try:

        subscription = request.get_json()

        if not subscription:

            return jsonify({
                "success": False,
                "message": "No subscription data received"
            }), 400

        endpoint = subscription.get("endpoint")

        if not endpoint:

            return jsonify({
                "success": False,
                "message": "Subscription endpoint is missing"
            }), 400

        # Save/update the subscription for the logged-in user
        push_subscriptions.update_one(

            {
                "user_id": session["user_id"],
                "subscription.endpoint": endpoint
            },

            {
                "$set": {
                    "user_id": session["user_id"],
                    "subscription": subscription,
                    "updated_at": datetime.now()
                }
            },

            upsert=True
        )

        return jsonify({
            "success": True,
            "message": "Push subscription saved successfully"
        })

    except Exception as e:

        print(
            "Save subscription error:",
            e
        )

        return jsonify({
            "success": False,
            "message": "Failed to save subscription"
        }), 500

@app.route("/eat_first")
def eat_first():

    if "user_id" not in session:
        return redirect("/")

    foods = list(collection.find({
        "user_id": session["user_id"]
    }))

    recommendations = []

    today = datetime.now().date()

    for food in foods:

        try:
            expiry_date = datetime.strptime(
                food["expiry"],
                "%Y-%m-%d"
            ).date()

            days_left = (
                expiry_date - today
            ).days

        except Exception:
            continue


        quantity = food.get(
            "quantity",
            "1"
        )

        category = food.get(
            "category",
            "Other"
        )

        storage = food.get(
            "storage_location",
            "Room Temperature"
        )


        priority = predict_priority(
            days_left,
            quantity,
            category,
            storage
        )


        recommendations.append({
            "food_name": food.get(
                "food_name",
                "Unknown"
            ),

            "category": category,

            "quantity": quantity,

            "storage_location": storage,

            "expiry": food.get(
                "expiry",
                ""
            ),

            "days_left": days_left,

            "priority": priority
        })


    # Sort HIGH → MEDIUM → LOW
    priority_order = {
        "HIGH": 1,
        "MEDIUM": 2,
        "LOW": 3
    }

    recommendations.sort(
        key=lambda x: (
            priority_order.get(
                x["priority"],
                4
            ),
            x["days_left"]
        )
    )


    return render_template(
        "eat_first.html",
        foods=recommendations
    )

@app.route("/waste_prevention")
def waste_prevention():

    if "user_id" not in session:
        return redirect("/")

    foods = list(collection.find({
        "user_id": session["user_id"]
    }))

    recommendations = []

    today = datetime.now().date()

    # =====================================================
    # CATEGORY-WISE WASTE PREVENTION TIPS
    # =====================================================

    waste_tips = {

        "dairy": [
            "Keep dairy products refrigerated.",
            "Keep containers properly sealed.",
            "Avoid leaving dairy products at room temperature for long periods.",
            "Use products with the nearest expiry date first.",
            "Check the product's condition before use."
        ],

        "milk": [
            "Keep milk refrigerated.",
            "Keep the milk container tightly closed.",
            "Avoid leaving milk at room temperature for extended periods.",
            "Use milk before its expiry date.",
            "Follow the storage instructions on the package."
        ],

        "cheese": [
            "Keep cheese refrigerated.",
            "Store cheese in a clean, sealed container.",
            "Avoid unnecessary temperature changes.",
            "Use cheese approaching its expiry date first.",
            "Check for unusual appearance or smell before use."
        ],

        "butter": [
            "Keep butter refrigerated according to its storage instructions.",
            "Keep butter covered to protect it from contamination.",
            "Avoid unnecessary exposure to heat.",
            "Use older butter before newly purchased butter.",
            "Check the expiry date regularly."
        ],

        "yogurt": [
            "Keep yogurt refrigerated.",
            "Keep the container sealed until use.",
            "Avoid leaving yogurt at room temperature for extended periods.",
            "Prioritize yogurt approaching its expiry date.",
            "Follow the storage instructions on the package."
        ],

        "fruits": [
            "Store fruits according to their storage requirements.",
            "Separate damaged or spoiled fruits.",
            "Use ripe fruits before less-ripe fruits.",
            "Avoid unnecessary bruising during storage.",
            "Check stored fruits regularly for spoilage."
        ],

        "vegetables": [
            "Store vegetables according to their storage requirements.",
            "Remove spoiled portions promptly.",
            "Prioritize vegetables with a shorter shelf life.",
            "Avoid excessive moisture where inappropriate.",
            "Check vegetables regularly for spoilage."
        ],

        "leafy vegetables": [
            "Store leafy vegetables appropriately in the refrigerator.",
            "Remove damaged or wilted leaves.",
            "Keep them clean and protected from contamination.",
            "Use leafy vegetables while they are fresh.",
            "Prioritize them when their freshness is declining."
        ],

        "potatoes": [
            "Store potatoes in a cool, dry and dark place.",
            "Keep potatoes away from excessive moisture.",
            "Provide proper ventilation during storage.",
            "Separate damaged or spoiled potatoes.",
            "Check regularly for sprouting or spoilage."
        ],

        "onions": [
            "Store onions in a cool, dry and well-ventilated place.",
            "Keep onions away from excessive moisture.",
            "Avoid storing damaged onions with healthy ones.",
            "Use older onions before newly purchased ones.",
            "Check regularly for soft or spoiled onions."
        ],

        "tomatoes": [
            "Store tomatoes according to their ripeness.",
            "Handle tomatoes carefully to avoid bruising.",
            "Use ripe tomatoes first.",
            "Separate damaged tomatoes from fresh ones.",
            "Check regularly for signs of spoilage."
        ],

        "grains": [
            "Store grains in a clean and dry container.",
            "Keep grain containers tightly sealed.",
            "Protect grains from moisture.",
            "Protect stored grains from insects and pests.",
            "Use older stock before newly purchased stock."
        ],

        "rice": [
            "Store rice in a dry and airtight container.",
            "Protect rice from moisture.",
            "Keep the storage area clean and dry.",
            "Check stored rice for insects or infestation.",
            "Use older rice stock before newly purchased stock."
        ],

        "wheat": [
            "Store wheat in a clean, dry and airtight container.",
            "Protect wheat from moisture.",
            "Keep wheat protected from insects and pests.",
            "Check stored wheat regularly.",
            "Use older stock before newly purchased stock."
        ],

        "flour": [
            "Store flour in a dry and airtight container.",
            "Protect flour from moisture.",
            "Keep flour away from insects and pests.",
            "Avoid storing flour in humid conditions.",
            "Check its condition before use."
        ],

        "pulses": [
            "Store pulses in a clean and dry container.",
            "Keep pulse containers airtight.",
            "Protect pulses from moisture.",
            "Check regularly for insects or infestation.",
            "Use older stock before newly purchased stock."
        ],

        "lentils": [
            "Store lentils in an airtight container.",
            "Keep lentils away from moisture.",
            "Protect them from insects and pests.",
            "Keep the storage area clean and dry.",
            "Check their condition before cooking."
        ],

        "spices": [
            "Store spices in a cool and dry place.",
            "Keep spice containers tightly closed.",
            "Protect spices from moisture.",
            "Avoid direct exposure to heat and humidity.",
            "Use older spices before newly purchased ones."
        ],

        "bakery": [
            "Keep bakery products properly sealed.",
            "Protect bakery products from excessive moisture.",
            "Store them according to their product instructions.",
            "Prioritize products approaching their expiry date.",
            "Check for visible spoilage before use."
        ],

        "bread": [
            "Keep bread properly sealed.",
            "Protect bread from excessive moisture.",
            "Store bread according to package instructions.",
            "Use bread before its expiry date.",
            "Check for visible mold before consumption."
        ],

        "biscuits": [
            "Keep biscuits in an airtight container after opening.",
            "Protect biscuits from moisture.",
            "Keep the storage container clean and dry.",
            "Use opened packets before newly purchased ones.",
            "Check the expiry date before consumption."
        ],

        "meat": [
            "Keep meat refrigerated or frozen as appropriate.",
            "Avoid leaving meat at room temperature for extended periods.",
            "Keep raw meat separate from ready-to-eat food.",
            "Follow the storage instructions on the package.",
            "Use meat according to its recommended use-by date."
        ],

        "chicken": [
            "Keep chicken refrigerated or frozen as appropriate.",
            "Avoid leaving chicken at room temperature for extended periods.",
            "Keep raw chicken separate from other foods.",
            "Follow the package storage instructions.",
            "Use chicken according to its recommended use-by date."
        ],

        "fish": [
            "Keep fish properly refrigerated or frozen.",
            "Avoid unnecessary temperature changes.",
            "Keep raw fish separate from other foods.",
            "Follow the product storage instructions.",
            "Use fish according to its recommended use-by date."
        ],

        "eggs": [
            "Store eggs according to the package storage instructions.",
            "Handle eggs carefully to avoid cracks.",
            "Keep eggs protected from contamination.",
            "Prioritize eggs approaching their use-by date.",
            "Check cracked or damaged eggs before use."
        ],

        "canned food": [
            "Store unopened cans in a cool and dry place.",
            "Keep cans away from excessive moisture.",
            "Check the expiry or best-before date.",
            "Avoid using badly damaged or swollen cans.",
            "After opening, follow the product's storage instructions."
        ],

        "frozen food": [
            "Keep frozen food at the recommended frozen temperature.",
            "Avoid unnecessary thawing.",
            "Follow the package storage instructions.",
            "Keep the freezer organized for easy identification.",
            "Prioritize items approaching their recommended date."
        ],

        "beverages": [
            "Store beverages according to package instructions.",
            "Keep opened beverages properly sealed.",
            "Avoid unnecessary exposure to heat.",
            "Check the expiry date regularly.",
            "Use opened beverages according to their storage instructions."
        ],

        "ready-to-eat food": [
            "Store ready-to-eat food according to its storage requirements.",
            "Keep food covered and protected from contamination.",
            "Avoid leaving it at room temperature for extended periods.",
            "Prioritize items with the nearest expiry date.",
            "Follow the storage instructions provided with the food."
        ],

        "general": [
            "Check the expiry date regularly.",
            "Store the food according to its storage requirements.",
            "Keep food protected from contamination.",
            "Prioritize food with the nearest expiry date.",
            "Follow the storage instructions provided with the product."
        ]
    }


    # =====================================================
    # PROCESS EACH FOOD
    # =====================================================

    for food in foods:

        try:

            expiry_date = datetime.strptime(
                food["expiry"],
                "%Y-%m-%d"
            ).date()

            days_left = (
                expiry_date - today
            ).days

        except Exception:

            continue


        quantity = food.get(
            "quantity",
            "1"
        )

        category = food.get(
            "category",
            "Other"
        )

        storage = food.get(
            "storage_location",
            "Room Temperature"
        )


        # =================================================
        # ML WASTE RISK
        # =================================================

        risk = predict_waste_risk(
            days_left,
            quantity,
            category,
            storage
        )


        # =================================================
        # GET CATEGORY-SPECIFIC TIPS
        # =================================================

        category_key = str(
            category
        ).strip().lower()

        tips = waste_tips.get(
            category_key,
            waste_tips["general"]
        )


        # =================================================
        # ADD RISK-SPECIFIC TIP
        # =================================================

        if risk == "HIGH":

            tips = [
                "Consume this food as soon as possible."
            ] + tips

        elif risk == "MEDIUM":

            tips = [
                "Plan to consume this food soon."
            ] + tips

        else:

            tips = [
                "Continue monitoring this food."
            ] + tips


        recommendations.append({

            "food_name": food.get(
                "food_name",
                "Unknown"
            ),

            "quantity": quantity,

            "category": category,

            "storage_location": storage,

            "expiry": food.get(
                "expiry",
                ""
            ),

            "days_left": days_left,

            "risk": risk,

            "tips": tips
        })


    # =====================================================
    # SORT HIGH → MEDIUM → LOW
    # =====================================================

    risk_order = {
        "HIGH": 1,
        "MEDIUM": 2,
        "LOW": 3
    }

    recommendations.sort(
        key=lambda x: (
            risk_order.get(
                x["risk"],
                4
            ),
            x["days_left"]
        )
    )


    return render_template(
        "waste_prevention.html",
        foods=recommendations
    )
# =========================
# ================================
# START EXPIRY THREAD
# =========================================================

# The desktop expiry checker should run locally only. On Render, browser
# push notifications require a separate scheduled job rather than a GUI thread.
if not os.getenv("RENDER"):
    threading.Thread(target=check_expiry, daemon=True).start()


# =========================================================
# RUN APP
# =========================================================

if __name__ == "__main__":
    app.run(debug=True)

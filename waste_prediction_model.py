import random
import re

from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline


# -----------------------------------------
# TRAINING DATA
# -----------------------------------------

categories = [
    "Dairy",
    "Vegetable",
    "Fruit",
    "Grain",
    "Bakery",
    "Meat",
    "Other"
]

storage_locations = [
    "Refrigerator",
    "Freezer",
    "Room Temperature",
    "Kitchen Shelf",
    "Cupboard"
]


X = []
y = []


# Generate sample training data

for _ in range(1500):

    days_left = random.randint(0, 30)

    quantity = round(
        random.uniform(0.5, 10),
        2
    )

    category = random.choice(
        categories
    )

    storage = random.choice(
        storage_locations
    )


    # Create initial training labels

    if days_left <= 2 and quantity >= 2:
        risk = "HIGH"

    elif days_left <= 2:
        risk = "MEDIUM"

    elif days_left <= 7 and quantity >= 3:
        risk = "HIGH"

    elif days_left <= 7:
        risk = "MEDIUM"

    else:
        risk = "LOW"


    X.append([
        days_left,
        quantity,
        category,
        storage
    ])

    y.append(risk)


# -----------------------------------------
# PREPROCESSING
# -----------------------------------------

preprocessor = ColumnTransformer(
    transformers=[

        (
            "category",
            OneHotEncoder(
                handle_unknown="ignore"
            ),
            [2]
        ),

        (
            "storage",
            OneHotEncoder(
                handle_unknown="ignore"
            ),
            [3]
        )

    ],

    remainder="passthrough"
)


# -----------------------------------------
# RANDOM FOREST MODEL
# -----------------------------------------

model = Pipeline([

    (
        "preprocessor",
        preprocessor
    ),

    (
        "classifier",
        RandomForestClassifier(
            n_estimators=100,
            random_state=42
        )
    )

])


model.fit(X, y)


# -----------------------------------------
# EXTRACT NUMBER FROM QUANTITY
# -----------------------------------------

def extract_quantity(quantity):

    if not quantity:
        return 1

    match = re.search(
        r"\d+(?:\.\d+)?",
        str(quantity)
    )

    if match:
        return float(
            match.group()
        )

    return 1


# -----------------------------------------
# PREDICT WASTE RISK
# -----------------------------------------

def predict_waste_risk(
    days_left,
    quantity,
    category,
    storage
):

    quantity_value = extract_quantity(
        quantity
    )

    prediction = model.predict([
        [
            days_left,
            quantity_value,
            category,
            storage
        ]
    ])

    return prediction[0]
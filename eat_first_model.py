import random
import re

from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline


# -----------------------------------------
# CREATE TRAINING DATA
# -----------------------------------------

categories = [
    "Dairy",
    "Vegetables",
    "Fruits",
    "Grains",
    "Bakery",
    "Meat",
    "Other"
]

storage_locations = [
    "Refrigerator",
    "Freezer",
    "Kitchen Shelf",
    "Cupboard",
    "Room Temperature"
]


X = []
y = []


# Generate sample training data
for _ in range(1000):

    days_left = random.randint(0, 30)
    quantity = round(random.uniform(0.5, 10), 2)

    category = random.choice(categories)
    storage = random.choice(storage_locations)

    # Priority logic used to create initial training examples
    if days_left <= 2:
        priority = "HIGH"

    elif days_left <= 7:
        priority = "MEDIUM"

    else:
        priority = "LOW"

    X.append([
        days_left,
        quantity,
        category,
        storage
    ])

    y.append(priority)


# -----------------------------------------
# ML MODEL
# -----------------------------------------

preprocessor = ColumnTransformer(
    transformers=[
        (
            "category",
            OneHotEncoder(handle_unknown="ignore"),
            [2]
        ),
        (
            "storage",
            OneHotEncoder(handle_unknown="ignore"),
            [3]
        )
    ],
    remainder="passthrough"
)


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
# QUANTITY EXTRACTION
# -----------------------------------------

def extract_quantity(quantity_text):

    if not quantity_text:
        return 1

    match = re.search(
        r"\d+(?:\.\d+)?",
        str(quantity_text)
    )

    if match:
        return float(match.group())

    return 1


# -----------------------------------------
# PREDICT PRIORITY
# -----------------------------------------

def predict_priority(
    days_left,
    quantity,
    category,
    storage
):

    quantity_value = extract_quantity(quantity)

    prediction = model.predict([
        [
            days_left,
            quantity_value,
            category,
            storage
        ]
    ])

    return prediction[0]
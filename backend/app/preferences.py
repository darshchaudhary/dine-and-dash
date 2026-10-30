"""Small content-based learner for sparse explicit feedback.

Exact dislikes remain hard exclusions elsewhere. Similarity only affects ranking;
it never infers allergies, dietary labels or nutrition values.
"""
from functools import lru_cache
import math
import re

STOPWORDS = {"a", "and", "the", "with", "in", "of", "oz", "ounce", "sliced", "diced", "chopped", "fresh", "cooked", "ckd", "cnd", "fz"}
FEATURES = {"chicken", "beef", "pork", "tofu", "fish", "shrimp", "rice", "quinoa", "mushroom", "broccoli", "bbq", "curry", "teriyaki", "spicy", "shawarma"}


@lru_cache(maxsize=8192)
def features(name):
    tokens = {word for word in re.findall(r"[a-z]+", name.casefold()) if word not in STOPWORDS and len(word) > 2}
    return {word: 2.0 if word in FEATURES else 1.0 for word in tokens}


def predict_affinities(foods, examples):
    output = {}
    observations = [(features(name), rating) for name, rating in examples if rating]
    for food in foods:
        candidate = features(food.name)
        norm = math.sqrt(sum(value * value for value in candidate.values()))
        positive, negative = 0.0, 0.0
        for observed, rating in observations:
            denominator = norm * math.sqrt(sum(value * value for value in observed.values()))
            similarity = sum(value * observed.get(word, 0) for word, value in candidate.items()) / denominator if denominator else 0
            if rating > 0:
                positive = max(positive, similarity)
            else:
                negative = max(negative, similarity)
        output[food.id] = positive - negative
    return output

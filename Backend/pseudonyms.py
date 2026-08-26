import random

ADJECTIVES = [
    "Quiet", "Restless", "Curious", "Wandering", "Sleepy", "Bold", "Hidden",
    "Lucky", "Silent", "Cheerful", "Fierce", "Gentle", "Sunny", "Midnight",
    "Rogue", "Nimble", "Salty", "Cosmic", "Drowsy", "Plucky",
]

NOUNS = [
    "Owl", "Comet", "Otter", "Falcon", "Lantern", "Cactus", "Heron", "Tide",
    "Ember", "Wren", "Nimbus", "Sparrow", "Beetle", "Glacier", "Finch",
    "Marmot", "Coral", "Pixel", "Lynx", "Meridian",
]


def generate_pseudonym() -> str:
    return f"{random.choice(ADJECTIVES)} {random.choice(NOUNS)}"

"""
Image-association pool.

Each image maps to an everyday object and a cue word. In the morning, the user
is shown the image + cue word. In the evening, the user is shown the cue word
alone and asked to type the object (or vice versa, depending on variant).
"""

from sqlalchemy import Column, Integer, String
from app.database import Base


class ImageAssociation(Base):
    __tablename__ = "image_associations"

    id = Column(Integer, primary_key=True, index=True)
    object_name = Column(String, nullable=False)   # e.g. "apple"
    cue_word = Column(String, nullable=False)      # e.g. "fruit"
    image_path = Column(String, nullable=False)    # relative path served by FastAPI static
    category = Column(String, nullable=False)      # e.g. "food", "household", "tool"


# Seed data -- 30 everyday items so we can sample 5 each morning
DEFAULT_ASSOCIATIONS = [
    ("apple",       "fruit",        "apple.png",       "food"),
    ("bread",       "bakery",       "bread.png",       "food"),
    ("carrot",      "vegetable",    "carrot.png",      "food"),
    ("chair",       "furniture",    "chair.png",       "household"),
    ("lamp",        "light",        "lamp.png",        "household"),
    ("book",        "reading",      "book.png",        "household"),
    ("phone",       "device",       "phone.png",       "device"),
    ("laptop",      "work",         "laptop.png",      "device"),
    ("keys",        "door",         "keys.png",        "household"),
    ("wallet",      "money",        "wallet.png",      "household"),
    ("umbrella",    "rain",         "umbrella.png",    "weather"),
    ("glasses",     "vision",       "glasses.png",     "health"),
    ("watch",       "time",         "watch.png",       "device"),
    ("shoes",       "walking",      "shoes.png",       "clothing"),
    ("jacket",      "cold",         "jacket.png",      "clothing"),
    ("cup",         "coffee",       "cup.png",         "household"),
    ("plate",       "meal",         "plate.png",       "household"),
    ("fork",        "eating",       "fork.png",        "household"),
    ("broom",       "cleaning",     "broom.png",       "tool"),
    ("hammer",      "tool",         "hammer.png",      "tool"),
    ("scissors",    "cutting",      "scissors.png",    "tool"),
    ("toothbrush",  "hygiene",      "toothbrush.png",  "health"),
    ("pencil",      "writing",      "pencil.png",      "tool"),
    ("envelope",    "mail",         "envelope.png",    "household"),
    ("clock",       "time",         "clock.png",       "household"),
    ("mirror",      "reflection",   "mirror.png",      "household"),
    ("bottle",      "water",        "bottle.png",      "household"),
    ("flower",      "garden",       "flower.png",      "nature"),
    ("dog",         "pet",          "dog.png",         "animal"),
    ("cat",         "pet",          "cat.png",         "animal"),
]


def seed_associations(session):
    """Idempotent: populate the image-association pool if empty."""
    if session.query(ImageAssociation).count() > 0:
        return
    for obj, cue, path, cat in DEFAULT_ASSOCIATIONS:
        session.add(
            ImageAssociation(
                object_name=obj,
                cue_word=cue,
                image_path=path,
                category=cat,
            )
        )
    session.commit()

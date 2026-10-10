"""Text utility functions for rule-based prompt review.

Provides pure-Python tokenization, stopword filtering, and descriptor
extraction to replace heavy NLP dependencies like spaCy.
"""
import re
from typing import Set

# Core English stopwords and common prepositions/conjunctions
STOPWORDS: Set[str] = {
    "the", "a", "an", "is", "was", "were", "with", "and", "her", "his", "their",
    "she", "he", "it", "in", "on", "at", "to", "of", "for", "as", "by", "from",
    "that", "this", "into", "while", "then", "who", "which", "toward", "over",
    "under", "through", "across", "up", "down", "out", "about", "above", "below",
    "behind", "beside", "between", "beyond", "but", "or", "nor", "yet", "so",
    "be", "been", "being", "have", "has", "had", "do", "does", "did", "are",
    "am", "i", "you", "we", "they", "my", "your", "our", "its",
}

# Common action verbs that don't describe physical attributes
# (we want to filter these out to focus on adjectives/nouns)
ACTION_VERBS: Set[str] = {
    "walks", "walk", "walking", "stands", "stand", "standing",
    "looks", "look", "looking", "turns", "turn", "turning",
    "moves", "move", "moving", "runs", "run", "running",
    "sits", "sit", "sitting", "talks", "talk", "talking",
    "speaks", "speak", "speaking", "smiles", "smile", "smiling",
    "laughs", "laugh", "laughing", "holds", "hold", "holding",
    "points", "point", "pointing", "watches", "watch", "watching",
    "sees", "see", "seeing", "hears", "hear", "hearing",
    "takes", "take", "taking", "gives", "give", "giving",
    "opens", "open", "opening", "closes", "close", "closing",
    "enters", "enter", "entering", "exits", "exit", "exiting",
}

# Domain-specific visual attribute vocabulary (high priority descriptors)
# If these conflict between shots, it's a strong signal of continuity drift.
ATTRIBUTE_VOCAB: Set[str] = {
    # Colors
    "black", "white", "red", "blue", "green", "yellow", "orange", "purple",
    "pink", "brown", "grey", "gray", "silver", "gold", "blonde", "brunette",
    "auburn", "crimson", "navy", "teal", "cyan", "magenta",
    # Materials
    "satin", "cotton", "leather", "linen", "silk", "denim", "wool",
    "velvet", "polyester", "nylon", "lace", "plastic", "metal", "wood",
    "glass", "concrete", "marble", "brick", "stone",
    # Physical traits / styles
    "tall", "short", "fat", "thin", "skinny", "muscular", "bald",
    "bearded", "mustache", "glasses", "sunglasses", "hat", "cap",
    "elegant", "casual", "formal", "messy", "neat", "clean", "dirty",
}

def extract_descriptors(text: str) -> Set[str]:
    """Extract descriptive tokens from text using pure Python rules."""
    if not text:
        return set()
    
    # Simple regex tokenization (words only)
    tokens = re.findall(r"[a-z']+", text.lower())
    
    descriptors = set()
    for t in tokens:
        # Strip trailing/leading punctuation artifacts if any sneaked through
        t = t.strip("'")
        
        # Filter rules:
        # 1. Length >= 3
        # 2. Not a stopword
        # 3. Not a common action verb
        if len(t) >= 3 and t not in STOPWORDS and t not in ACTION_VERBS:
            descriptors.add(t)
            
    return descriptors

def find_conflicting_attributes(tokens_a: Set[str], tokens_b: Set[str]) -> tuple[Set[str], Set[str]]:
    """Return specific known-attribute vocabulary words that exist in one set but not the other.
    Useful for detecting high-confidence conflicts (e.g. 'blonde' vs 'brunette')."""
    attrs_a = tokens_a & ATTRIBUTE_VOCAB
    attrs_b = tokens_b & ATTRIBUTE_VOCAB
    
    # If a shot has NO specific attributes from our vocab, we can't definitively say it conflicts
    # based purely on the vocab (e.g. one shot says "red shirt", another just says "shirt").
    # A true conflict is when both have known attributes, and they don't overlap, 
    # but for broad flagging, we just return the unique attributes on each side.
    unique_a = attrs_a - attrs_b
    unique_b = attrs_b - attrs_a
    
    return unique_a, unique_b

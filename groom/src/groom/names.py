"""Helpers for turning folder and file name fragments into values."""

import re

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16,
}  # fmt: skip
_WORD_RE = re.compile("|".join(sorted(_NUMBER_WORDS, key=len, reverse=True)), re.IGNORECASE)

KIND_TOKENS = {
    "grv": "groove",
    "groove": "groove",
    "fill": "fill",
    "brk": "break",
    "break": "break",
    "crsh": "ending",
    "ending": "ending",
    "intro": "intro",
}


def meter_from_words(text: str) -> tuple[int, int] | None:
    """'SevenEight', 'Seven Eight' or 'NineEight_Drums' -> (7, 8)."""
    words = _WORD_RE.findall(text)
    if len(words) < 2:
        return None
    num, den = _NUMBER_WORDS[words[0].lower()], _NUMBER_WORDS[words[1].lower()]
    return (num, den) if den in (2, 4, 8, 16) else None


def kind_from_token(token: str | None) -> str | None:
    return KIND_TOKENS.get(token.lower()) if token else None


def split_camel(text: str) -> str:
    """'StraightUpGroove' -> 'Straight Up Groove'; underscores become spaces."""
    text = text.replace("_", " ")
    text = re.sub(r"(?<=[a-z])(?=[A-Z0-9])|(?<=[0-9])(?=[A-Z][a-z])", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def match_key(text: str) -> str:
    """Normalised form for fuzzy matching: lowercase letters and digits only."""
    return re.sub(r"[^a-z0-9]", "", text.lower())

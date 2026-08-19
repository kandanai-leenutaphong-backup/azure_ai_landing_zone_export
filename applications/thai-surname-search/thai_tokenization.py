from __future__ import annotations

import unicodedata

from pythainlp.tokenize import word_tokenize


def tokenize_thai(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFC", str(text)).casefold().strip()
    return [
        token.strip()
        for token in word_tokenize(
            normalized, engine="newmm", keep_whitespace=False
        )
        if token.strip()
    ]

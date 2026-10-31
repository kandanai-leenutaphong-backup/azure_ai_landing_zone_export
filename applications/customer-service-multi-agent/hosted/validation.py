"""Synthetic-only boundary, shared by frontend service and Hosted runtime."""
import re

# Obvious real contact/payment payloads and import requests are refused before inference.
# Not a general-purpose PII detector. Caller must supply synthetic text only.
PRIVATE_DATA = re.compile(
    r"https?://|[\w.+-]+@[\w.-]+\.[a-z]{2,}|(?:\d[ -]?){13,19}"
    r"|\b(?:import|upload)\b.{0,100}\b(?:csv|xlsx|customers?|records?)\b",
    re.IGNORECASE,
)


def validate_message(message):
    if not isinstance(message, str) or not 1 <= len(message) <= 2000 or not message.strip():
        raise ValueError("message_length_1_to_2000")
    if PRIVATE_DATA.search(message):
        raise ValueError("synthetic_details_only")

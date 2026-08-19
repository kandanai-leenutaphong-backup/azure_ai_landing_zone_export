import os
from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures
from azure.identity import DefaultAzureCredential

ENDPOINT = os.getenv("AZURE_CV_ENDPOINT", "")


def get_ocr_client() -> ImageAnalysisClient:
    """Build an ImageAnalysisClient using DefaultAzureCredential (no API key needed)."""
    credential = DefaultAzureCredential()
    return ImageAnalysisClient(endpoint=ENDPOINT, credential=credential)


# Module-level client (lazy init)
_client_OCR: ImageAnalysisClient | None = None


def _get_client() -> ImageAnalysisClient:
    global _client_OCR
    if _client_OCR is None:
        _client_OCR = get_ocr_client()
    return _client_OCR


def core_id_card(image_data: bytes) -> dict:
    """
    Run OCR on ID card image bytes and return structured text blocks.

    Args:
        image_data: Raw image bytes (JPEG, PNG, BMP, etc.)

    Returns:
        dict with 'lines' (list of str) and 'words' (list of dict with text + confidence)
    """
    client = _get_client()

    extracted_result = client.analyze(
        image_data=image_data,
        visual_features=[VisualFeatures.READ],
    )

    lines = []
    words = []

    if extracted_result.read is not None:
        for block in extracted_result.read.blocks:
            for line in block.lines:
                lines.append(line.text)
                for word in line.words:
                    words.append(
                        {
                            "text": word.text,
                            "confidence": word.confidence,
                            "bounding_polygon": [
                                {"x": p.x, "y": p.y} for p in word.bounding_polygon
                            ],
                        }
                    )

    return {
        "lines": lines,
        "words": words,
        "model_version": extracted_result.model_version,
        "metadata": {
            "width": extracted_result.metadata.width if extracted_result.metadata else None,
            "height": extracted_result.metadata.height if extracted_result.metadata else None,
        },
    }


def core_id_card_from_url(image_url: str) -> dict:
    """
    Run OCR on an ID card image referenced by URL.

    Args:
        image_url: Publicly accessible HTTPS URL of the image.

    Returns:
        Same structure as core_id_card().
    """
    client = _get_client()

    extracted_result = client.analyze_from_url(
        image_url=image_url,
        visual_features=[VisualFeatures.READ],
    )

    lines = []
    words = []

    if extracted_result.read is not None:
        for block in extracted_result.read.blocks:
            for line in block.lines:
                lines.append(line.text)
                for word in line.words:
                    words.append(
                        {
                            "text": word.text,
                            "confidence": word.confidence,
                            "bounding_polygon": [
                                {"x": p.x, "y": p.y} for p in word.bounding_polygon
                            ],
                        }
                    )

    return {
        "lines": lines,
        "words": words,
        "model_version": extracted_result.model_version,
        "metadata": {
            "width": extracted_result.metadata.width if extracted_result.metadata else None,
            "height": extracted_result.metadata.height if extracted_result.metadata else None,
        },
    }


if __name__ == "__main__":
    import sys
    import json

    # Usage: python ocr_functions.py [image_path_or_url]
    # With no argument, tests connectivity using a sample public image.
    sample = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "https://learn.microsoft.com/azure/ai-services/computer-vision/media/quickstarts/presentation.png"
    )

    print(f"Endpoint : {ENDPOINT}")
    print(f"Input    : {sample}")
    print("Authenticating via DefaultAzureCredential ...")

    if sample.startswith("http://") or sample.startswith("https://"):
        result = core_id_card_from_url(sample)
    else:
        with open(sample, "rb") as f:
            result = core_id_card(f.read())

    print("\n--- OCR Result ---")
    print(json.dumps(result, indent=2))

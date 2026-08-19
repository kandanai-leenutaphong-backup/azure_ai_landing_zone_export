import json
import os
import socket
import time
from urllib.parse import urlparse
import streamlit as st
from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures
from azure.identity import DefaultAzureCredential

DEFAULT_ENDPOINT = os.getenv("AZURE_CV_ENDPOINT", "")
DEFAULT_IMAGE_URL = "https://learn.microsoft.com/azure/ai-services/computer-vision/media/quickstarts/presentation.png"

st.set_page_config(page_title="Azure CV OCR Tester", layout="wide")
st.title("Azure Computer Vision — OCR Tester")

# ── Sidebar inputs ────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Configuration")
    endpoint = st.text_input("CV Endpoint", value=DEFAULT_ENDPOINT)
    image_url = st.text_input("Image URL", value=DEFAULT_IMAGE_URL)
    runs = st.number_input("Repeat N times", min_value=1, max_value=50, value=5, step=1)
    run_btn = st.button("Run OCR", type="primary", use_container_width=True)
    st.divider()
    nslookup_btn = st.button("NS Lookup", use_container_width=True)

# ── Helpers ───────────────────────────────────────────────────────────────────

def nslookup(url: str) -> dict:
    """Resolve hostname from a URL, following CNAME chain."""
    hostname = urlparse(url).hostname or url
    result = {"hostname": hostname, "addresses": [], "cname_chain": [], "error": None}
    try:
        # getaddrinfo returns all A/AAAA records
        infos = socket.getaddrinfo(hostname, None)
        result["addresses"] = sorted({i[4][0] for i in infos})
        # Follow CNAME chain via successive canonical name lookups
        name = hostname
        seen = set()
        while True:
            try:
                canonical = socket.getfqdn(name)
                if canonical == name or canonical in seen:
                    break
                result["cname_chain"].append(f"{name} → {canonical}")
                seen.add(canonical)
                name = canonical
            except Exception:
                break
    except socket.gaierror as e:
        result["error"] = str(e)
    return result


@st.cache_resource(show_spinner=False)
def build_client(ep: str) -> ImageAnalysisClient:
    return ImageAnalysisClient(endpoint=ep, credential=DefaultAzureCredential())


def call_ocr(client: ImageAnalysisClient, url: str) -> tuple[dict, float]:
    start = time.perf_counter()
    result = client.analyze_from_url(
        image_url=url,
        visual_features=[VisualFeatures.READ],
    )
    elapsed = time.perf_counter() - start

    lines, words = [], []
    if result.read:
        for block in result.read.blocks:
            for line in block.lines:
                lines.append(line.text)
                for word in line.words:
                    words.append({
                        "text": word.text,
                        "confidence": round(word.confidence, 4),
                        "bounding_polygon": [{"x": p.x, "y": p.y} for p in word.bounding_polygon],
                    })

    return {
        "lines": lines,
        "words": words,
        "model_version": result.model_version,
        "metadata": {
            "width": result.metadata.width if result.metadata else None,
            "height": result.metadata.height if result.metadata else None,
        },
    }, elapsed


# ── Main ──────────────────────────────────────────────────────────────────────
if nslookup_btn:
    for label, url in [("CV Endpoint", endpoint.strip()), ("Image URL", image_url.strip())]:
        if not url:
            continue
        st.subheader(f"NS Lookup — {label}")
        res = nslookup(url)
        st.markdown(f"**Hostname:** `{res['hostname']}`")
        if res["error"]:
            st.error(f"Resolution failed: {res['error']}")
        else:
            st.success(f"Resolved to: {', '.join(res['addresses'])}")
            if res["cname_chain"]:
                st.markdown("**CNAME chain:**")
                for step in res["cname_chain"]:
                    st.text(step)
        st.divider()

if run_btn:
    if not endpoint.strip():
        st.error("Please enter a CV endpoint.")
        st.stop()
    if not image_url.strip():
        st.error("Please enter an image URL.")
        st.stop()

    try:
        client = build_client(endpoint.strip())
    except Exception as e:
        st.error(f"Failed to build client: {e}")
        st.stop()

    st.subheader(f"Results — {runs} run(s)")
    st.image(image_url, caption="Input image", use_container_width=False, width=400)

    timings: list[float] = []
    results: list[dict] = []
    errors: list[str] = []

    progress = st.progress(0, text="Running…")

    for i in range(int(runs)):
        try:
            ocr_result, elapsed = call_ocr(client, image_url.strip())
            timings.append(elapsed)
            results.append(ocr_result)
        except Exception as e:
            errors.append(f"Run {i + 1}: {e}")
        progress.progress((i + 1) / int(runs), text=f"Run {i + 1} / {runs}")

    progress.empty()

    # ── Timing summary ────────────────────────────────────────────────────────
    if timings:
        avg = sum(timings) / len(timings)
        col1, col2, col3 = st.columns(3)
        col1.metric("Average", f"{avg:.3f}s")
        col2.metric("Min", f"{min(timings):.3f}s")
        col3.metric("Max", f"{max(timings):.3f}s")

        st.markdown("**Per-run response times**")
        timing_rows = [{"Run": i + 1, "Time (s)": f"{t:.3f}"} for i, t in enumerate(timings)]
        st.table(timing_rows)

    # ── Errors (if any) ───────────────────────────────────────────────────────
    if errors:
        st.error("Some runs failed:")
        for err in errors:
            st.text(err)

    # ── OCR output per run ────────────────────────────────────────────────────
    if results:
        st.markdown("---")
        st.subheader("OCR Output")
        for i, res in enumerate(results):
            with st.expander(f"Run {i + 1} — {timings[i]:.3f}s", expanded=(i == 0)):
                col_left, col_right = st.columns(2)
                with col_left:
                    st.markdown("**Extracted lines**")
                    for line in res["lines"]:
                        st.write(f"- {line}")
                with col_right:
                    st.markdown("**Raw JSON**")
                    st.code(json.dumps(res, indent=2), language="json")

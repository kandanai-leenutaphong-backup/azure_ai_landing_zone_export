#!/usr/bin/env python3
"""Capture local fixture responses through the real browser without contacting a website."""

from __future__ import annotations

import argparse
import io
import json
from importlib import import_module
import socket
import sys
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import webres

HTML = b'''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Acquisition fixture</title>
<style>body{margin:0;background:#f3f6f4;font-family:Georgia,serif}main{padding:24px;box-sizing:border-box;width:100%}
h1{font-size:24px;margin:0 0 20px;color:#172c25}img.asset{width:96px;height:96px}.band{height:80px;background:#bd3f52;margin-top:24px}</style>
</head><body><main><h1>Acquisition fixture</h1><img class="asset" src="https://fixture.example/asset.png" alt="Fixture asset">
<img src="http://127.0.0.1/private" alt="Blocked fixture"><div class="band"></div></main></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    arguments = parser.parse_args()
    arguments.out.mkdir(parents=True, exist_ok=True)
    image = io.BytesIO()
    Image.new("RGB", (96, 96), (23, 108, 82)).save(image, format="PNG")
    assets = {"https://fixture.example/": (HTML, "text/html"),
              "https://fixture.example/asset.png": (image.getvalue(), "image/png")}
    read_urls = []

    def resolve(host, port, **kwargs):
        address = "127.0.0.1" if host == "127.0.0.1" else "8.8.8.8"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port or 443))]

    def fixture_open(request, **kwargs):
        webres.validate_url(request.full_url)
        assert request.get_method() == "GET"
        if request.full_url not in assets:
            raise webres.AcquisitionError("undeclared fixture URL")
        payload, content_type = assets[request.full_url]
        response = io.BytesIO(payload)
        response.status = 200
        response.headers = {"Content-Type": content_type}
        read_urls.append(request.full_url)
        return response

    module = vars(import_module("webres.cli.capture_screenshot"))
    targets = [{"url": "https://fixture.example/", "name": name, "width": width, "height": height,
                "fullPage": False, "path": str(arguments.out / f"{name}.png")}
               for name, width, height in (("desktop", 1280, 720), ("mobile", 390, 844))]
    with patch.object(webres.socket, "getaddrinfo", side_effect=resolve), \
            patch.dict(module["fulfill_public"].__globals__, {"open_public": fixture_open}):
        results = module["capture"](targets)
    for target, result in zip(targets, results):
        assert result["ok"], result
        assert result["blocked_requests"] >= 1, result
        with Image.open(target["path"]) as captured:
            assert captured.size == (target["width"] * 2, target["height"] * 2), captured.size
            colors = captured.convert("RGB").getcolors(captured.width * captured.height)
            assert any(count > 100 and color == (23, 108, 82) for count, color in colors), "fixture image is blank"
            assert any(count > 100 and color == (189, 63, 82) for count, color in colors), "fixture band is absent"
    assert "http://127.0.0.1/private" not in read_urls
    report = {"passed": True, "views": results, "external_requests": 0, "asset_reads": read_urls}
    (arguments.out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PASS: desktop/mobile screenshots, visible fixture image, private-request refusal, no external network")


if __name__ == "__main__":
    main()
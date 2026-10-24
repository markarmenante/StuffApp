#!/usr/bin/env python3
"""Build web and native icons from the checked-in, unmodified source artwork."""

import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "assets/branding/stuffapp-source.png"
NATIVE = ROOT / "ios/StuffOfflineApp/Assets.xcassets/AppIcon.appiconset"


def build_outputs():
    source_bytes = SOURCE.read_bytes()
    revision = hashlib.sha256(source_bytes).hexdigest()[:12]
    source = Image.open(BytesIO(source_bytes)).convert("RGBA")
    if source.size != (1024, 1024):
        raise ValueError("Use the approved 1024 x 1024 source without cropping it.")
    outputs = {}
    desktop = BytesIO()
    source.save(desktop, format="ICNS", append_images=[
        source.resize((size, size), Image.Resampling.LANCZOS)
        for size in (32, 64, 128, 256, 512)
    ])
    outputs[ROOT / "assets/branding/stuffapp.icns"] = desktop.getvalue()

    def png(path, size, opaque=False):
        image = source.resize((size, size), Image.Resampling.LANCZOS)
        if opaque:
            # The existing default iOS asset catalog requires an opaque icon.
            # This exception does not apply to web or Apple touch icons.
            background = Image.new("RGBA", image.size, "white")
            image = Image.alpha_composite(background, image).convert("RGB")
        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        outputs[path] = buffer.getvalue()

    png(ROOT / "static/img/icon-192.png", 192)
    png(ROOT / "static/img/icon-512.png", 512)
    png(ROOT / "static/img/apple-touch-icon.png", 180)
    catalog = json.loads((NATIVE / "Contents.json").read_text())
    for entry in catalog["images"]:
        width, height = map(float, entry["size"].split("x"))
        scale = float(entry["scale"].removesuffix("x"))
        assert width == height and (width * scale).is_integer()
        png(NATIVE / entry["filename"], int(width * scale), opaque=True)

    manifest_path = ROOT / "static/manifest.webmanifest"
    manifest = json.loads(manifest_path.read_text())
    for icon in manifest["icons"]:
        icon["src"] = icon["src"].split("?")[0] + "?v=" + revision
        # This is complete artwork, not designed for arbitrary mask cropping.
        icon["purpose"] = "any"
    outputs[manifest_path] = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode()
    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify generated files without writing")
    args = parser.parse_args()
    outputs = build_outputs()
    stale = [path for path, data in outputs.items()
             if not path.exists() or path.read_bytes() != data]
    if args.check:
        if stale:
            for path in stale:
                print(f"Needs regeneration: {path.relative_to(ROOT)}")
            raise SystemExit(1)
        print(f"Verified {len(outputs)} generated icon files and manifest from {SOURCE.relative_to(ROOT)}")
        return
    for path in stale:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(outputs[path])
    print(f"Updated {len(stale)} of {len(outputs)} generated icon files and manifest")


if __name__ == "__main__":
    main()

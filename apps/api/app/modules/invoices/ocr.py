"""Bounded local native processing; originals exist only in a private temporary directory."""

import io
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

MAX_BYTES = 5 * 1024 * 1024
MAX_TEXT = 100000
Image.MAX_IMAGE_PIXELS = 12000000


def availability():
    required = ("tesseract", "prlimit", "pdfinfo", "pdftoppm", "pdftotext")
    if not all(shutil.which(name) for name in required):
        return False
    try:
        result = subprocess.run(
            [shutil.which("tesseract"), "--list-langs"], capture_output=True, timeout=3, check=True
        )
        return {"fas", "eng"}.issubset(set(result.stdout.decode().splitlines()))
    except (OSError, subprocess.SubprocessError):
        return False


def extract(data, media_type):
    if not availability():
        raise HTTPException(
            503, "Local OCR dependencies or Persian/English language data unavailable"
        )
    deadline = time.monotonic() + 30
    with tempfile.TemporaryDirectory(prefix="steelos-invoice-") as directory:
        root = Path(directory)
        source = root / "source"
        source.write_bytes(data)

        def run(arguments, output=None):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HTTPException(504, "Local document processing deadline exceeded")
            command = [
                shutil.which("prlimit"),
                "--as=536870912",
                "--cpu=15",
                "--fsize=20971520",
                "--",
            ]
            command += [shutil.which(arguments[0]), *arguments[1:]]
            try:
                with open(output, "wb") if output else open(os.devnull, "wb") as stream:
                    result = subprocess.run(
                        command,
                        stdout=stream,
                        stderr=subprocess.DEVNULL,
                        env={**os.environ, "OMP_THREAD_LIMIT": "1", "LC_ALL": "C.UTF-8"},
                        timeout=remaining,
                        check=False,
                    )
                if result.returncode:
                    raise HTTPException(422, "Document could not be processed safely")
            except subprocess.TimeoutExpired:
                raise HTTPException(504, "Local document processing deadline exceeded") from None

        def read(path):
            if path.stat().st_size > MAX_TEXT * 4:
                raise HTTPException(422, "Extracted text exceeds limit")
            value = path.read_text(errors="replace")
            if len(value) > MAX_TEXT:
                raise HTTPException(422, "Extracted text exceeds limit")
            return value

        pages, engine = 1, "tesseract/eng+fas"
        if media_type == "application/pdf":
            if not data.startswith(b"%PDF-"):
                raise HTTPException(422, "Invalid PDF signature")
            info = root / "info"
            run(["pdfinfo", str(source)], info)
            metadata = read(info)
            found = re.findall(r"^Pages:[ \t]+(\d+)[ \t]*$", metadata, re.M)
            if (
                len(found) != 1
                or not 1 <= int(found[0]) <= 3
                or re.search(r"^Encrypted:\s+yes", metadata, re.M)
            ):
                raise HTTPException(422, "Only unencrypted PDFs with1–3 pages are supported")
            pages = int(found[0])
            text = root / "embedded.txt"
            run(["pdftotext", "-layout", "-f", "1", "-l", str(pages), str(source), str(text)])
            embedded = read(text).strip()
            if len(embedded) >= 20:
                return embedded, pages, "poppler/embedded-text"
            images = []
            for page in range(1, pages + 1):
                prefix = root / f"page-{page}"
                run(
                    [
                        "pdftoppm",
                        "-f",
                        str(page),
                        "-l",
                        str(page),
                        "-singlefile",
                        "-scale-to",
                        "2400",
                        "-png",
                        str(source),
                        str(prefix),
                    ]
                )
                images.append(Path(str(prefix) + ".png"))
        else:
            try:
                with Image.open(io.BytesIO(data)) as image:
                    expected = "PNG" if media_type == "image/png" else "JPEG"
                    if (
                        image.format != expected
                        or image.width * image.height > 12000000
                        or getattr(image, "n_frames", 1) != 1
                    ):
                        raise ValueError("Invalid image")
                    image.verify()
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
                raise HTTPException(422, "Invalid, oversized or unsupported image") from None
            images = [source]
        texts = []
        for index, image in enumerate(images):
            target = root / f"ocr-{index}"
            run(["tesseract", str(image), str(target), "-l", "eng+fas", "--psm", "6"])
            texts.append(read(Path(str(target) + ".txt")))
        combined = "\n\n".join(texts).strip()
        if len(combined) > MAX_TEXT:
            raise HTTPException(422, "Extracted text exceeds limit")
        return combined, pages, engine

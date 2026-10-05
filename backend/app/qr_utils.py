from __future__ import annotations

import base64
from io import BytesIO

import qrcode


def qr_png_base64(payload: str) -> str:
    image = qrcode.make(payload)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")

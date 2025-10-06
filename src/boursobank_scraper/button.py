import base64
from io import BytesIO
from typing import Optional

import cairosvg  # type: ignore
from PIL import Image
from playwright.sync_api import ElementHandle


class Button:
    def __init__(self, number: Optional[str], imgBase64Str: str) -> None:
        self.number = number
        self.imgBase64Str = imgBase64Str
        b64 = base64.b64decode(self.imgBase64Str)
        pngByteString = cairosvg.svg2png(bytestring=b64)  # type: ignore
        self.element: Optional[ElementHandle] = None
        if isinstance(pngByteString, bytes):
            buffered = BytesIO(pngByteString)
            self.image = Image.open(buffered).convert("RGB")

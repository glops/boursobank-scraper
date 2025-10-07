import base64
from typing import Optional

from playwright.sync_api import ElementHandle


class Button:
    def __init__(self, number: Optional[str], imgBase64Str: str) -> None:
        self.number = number
        self.imgBase64Str = imgBase64Str
        self.svgStr = base64.b64decode(self.imgBase64Str).decode("utf8")
        self.element: ElementHandle | None = None

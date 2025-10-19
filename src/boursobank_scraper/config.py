import msgspec


class Config(msgspec.Struct):
    username: int
    password: int | None = None
    headless: bool = True
    timeoutMs: int = 30000
    saveTrace: bool = False

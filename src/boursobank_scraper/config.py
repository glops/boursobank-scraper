import msgspec


class Config(msgspec.Struct):
    username: int
    password: int | None = None
    password_by_keyring: bool = False
    headless: bool = True
    timeoutMs: int = 30000
    saveTrace: bool = False

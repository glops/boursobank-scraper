import msgspec


class Config(msgspec.Struct):
    username: int
    password: int | None = None
    headless: bool = True

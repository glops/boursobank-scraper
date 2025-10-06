from decimal import Decimal

from msgspec import Struct


class BoursoAccount(Struct):
    id: str
    name: str
    balance: Decimal
    link: str

    def __str__(self) -> str:
        return f"{self.name} - {self.balance} - {self.id} - {self.link}"

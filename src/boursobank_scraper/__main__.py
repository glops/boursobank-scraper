import argparse
import getpass
import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import msgspec

from boursobank_scraper.account import BoursoAccount
from boursobank_scraper.bourso_scraper import BoursoScraper
from boursobank_scraper.config import Config


def selectAccounts(accounts: list[BoursoAccount]) -> list[BoursoAccount]:
    print("Comptes trouvés :")
    for i, account in enumerate(accounts):
        print(f"  {i} - {account.name} ({account.balance})")
    print("  a - Tous les comptes")

    while True:
        choice = input("Numéro du compte à exporter (ou 'a' pour tous) : ").strip().lower()
        if choice == "a":
            return accounts
        if choice.isdigit():
            index = int(choice)
            if 0 <= index < len(accounts):
                return [accounts[index]]
        print("Choix invalide, veuillez réessayer.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-folder",
        help="Chemin vers le répertoire de données. Si non spécifié, utilise le répertoire courant.",
    )
    parser.add_argument(
        "--select-account",
        action="store_true",
        help="Affiche la liste des comptes trouvés et demande lequel exporter.",
    )
    parser.add_argument(
        "--export-type",
        choices=["json", "ofx"],
        default="json",
        help="Type d'export : 'json' (par défaut, comportement actuel) ou 'ofx' (export via le bouton "
        "'Exporter les opérations' de la page du compte).",
    )
    args = parser.parse_args()

    rootDataPath = None
    if args.data_folder is not None:
        rootDataPath = Path(args.data_folder)
        if not rootDataPath.exists():
            print(f"Le répertoire '{rootDataPath}' n'existe pas.")
            exit(1)
        elif not rootDataPath.is_dir():
            print(f"'{rootDataPath}' n'est pas un répertoire.")
            exit(1)
    else:
        rootDataPath = Path.cwd()

    configPath = rootDataPath / "config.yaml"
    if not (rootDataPath / "config.yaml").exists():
        print(f"Le fichier de configuration '{configPath}' n'existe pas.")
        exit(1)

    config = msgspec.yaml.decode(configPath.read_text("utf8"), type=Config)

    if config.password is None:
        try:
            config.password = int(getpass.getpass("Password:"))
        except ValueError:
            print("Erreur : le mot de passe ne doit contenir que des chiffres")
            exit(1)

    logger = logging.getLogger(__name__)
    logPath = rootDataPath / "log" / f"import_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logPath.parent.mkdir(exist_ok=True)

    logging.basicConfig(filename=logPath, encoding="utf-8", level=logging.DEBUG)
    logging.getLogger().addHandler(logging.StreamHandler())

    logger.info(f"Headless mode: {config.headless}")
    logger.info(f"Data path: {rootDataPath}")
    try:
        boursoScraper = BoursoScraper(
            username=str(config.username),
            password=str(config.password),
            rootDataPath=rootDataPath,
            headless=config.headless,
            timeout=config.timeoutMs,
            saveTrace=config.saveTrace,
            ofxNbMonthsBefore=config.ofxNbMonthsBefore,
            ofxNbMonthsAfter=config.ofxNbMonthsAfter,
        )

        if boursoScraper.connect():
            if args.export_type == 'ofx' and not args.select_account:
                allAccount = BoursoAccount(
                    id="all",
                    name="all accounts",
                    balance=Decimal(0),
                    link=f"{boursoScraper.apiUrl}/budget/mouvements",
                )
                boursoScraper.saveAccountTransactionsAsOfx(allAccount)
            else:
                accounts = list(boursoScraper.listAccounts())
                accountsFilePath = rootDataPath / "accounts.json"
                accountsFilePath.write_bytes(msgspec.json.encode(accounts))

                if args.select_account:
                    accounts = selectAccounts(accounts)

                for account in accounts:
                    logger.info(f"{account.name} - {account.balance} - {account.id}")
                    logger.info(f"{account.link}")
                    if args.export_type == "ofx":
                        boursoScraper.saveAccountTransactionsAsOfx(account)
                    else:
                        boursoScraper.saveAccountTransactionsAsJson(account)

    finally:
        try:
            boursoScraper.stopTracing()  # type: ignore
            boursoScraper.close()  # type: ignore
        except Exception:
            pass


if __name__ == "__main__":
    main()

import argparse
import getpass
import logging
from datetime import datetime
from pathlib import Path

import msgspec

from boursobank_scraper.bourso_scraper import BoursoScraper
from boursobank_scraper.config import Config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-folder",
        help="Chemin vers le répertoire de données. Si non spécifié, utilise le répertoire courant.",
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
    logPath = (
        rootDataPath / "log" / f"import_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )
    logPath.parent.mkdir(exist_ok=True)

    logging.basicConfig(filename=logPath, encoding="utf-8", level=logging.DEBUG)
    logging.getLogger().addHandler(logging.StreamHandler())

    logger.info(f"Headless mode: {config.headless}")
    logger.info(f"Data path: {rootDataPath}")
    try:
        boursoScraper = BoursoScraper(
            str(config.username), str(config.password), rootDataPath, config.headless
        )

        if boursoScraper.connect():
            accounts = list(boursoScraper.listAccounts())
            accountsFilePath = rootDataPath / "accounts.json"
            accountsFilePath.write_bytes(msgspec.json.encode(accounts))
            for account in accounts:
                print(f"{account.name} - {account.balance} - {account.id}")
                print(f"{account.link}")
                boursoScraper.saveNewTransactionsForAccount(account)

    finally:
        try:
            boursoScraper.stopTracing()  # type: ignore
            boursoScraper.close()  # type: ignore
        except Exception:
            pass


if __name__ == "__main__":
    main()

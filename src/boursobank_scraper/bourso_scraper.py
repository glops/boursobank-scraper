import logging
import re
import time
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path

import msgspec
from playwright.sync_api import (
    BrowserContext,
    Locator,
    Page,
    TimeoutError,
    sync_playwright,
)

from boursobank_scraper.account import BoursoAccount
from boursobank_scraper.button import Button
from boursobank_scraper.models import BoursoApiOperation
from boursobank_scraper.reference_buttons import referenceButtons


class BoursoScraper:
    def __init__(
        self,
        username: str,
        password: str,
        rootDataPath: Path,
        headless: bool = True,
        timeout: int = 30000,
        saveTrace: bool = False,
    ):
        self.logger = logging.getLogger(__name__)

        self.apiUrl = "https://clients.boursobank.com"
        self.username = username
        self.password = password
        self.rootDataPath = rootDataPath
        self.timeout = timeout
        self.saveTrace = saveTrace
        self.debugPath = self.rootDataPath / "debug"
        self.debugPath.mkdir(exist_ok=True)
        self.transactionsPath = self.rootDataPath / "transactions"
        self.transactionsPath.mkdir(exist_ok=True)

        self.regexCleanAmount = re.compile(r"[^0-9,-]+", flags=re.I)

        self.contextFile = self.debugPath / "context.json"

        self.logger.debug("Start playwright and chromium")
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=headless, slow_mo=500)
        self.context: BrowserContext
        self.page: Page

    def close(self):
        self.logger.debug("Close browser and stop playwright")
        self.browser.close()
        self.playwright.stop()

    def orLocator(self, locators: list[Locator]):
        mergedLocator = locators[0]
        for i in range(1, len(locators)):
            mergedLocator = mergedLocator.or_(locators[i])

        return mergedLocator.first

    def cleanAmount(self, amountStr: str) -> Decimal:
        balanceClean = self.regexCleanAmount.sub("", amountStr).replace(",", ".")

        return Decimal(balanceClean).quantize(Decimal("1.00"))

    def connect(self) -> bool:
        try:
            if self.contextFile.is_file():
                self.logger.debug("Login state exists. Load it")
                contextFile = self.contextFile
            else:
                self.logger.debug("No state file exists. Try to login.")
                contextFile = None
            self.context = self.browser.new_context(storage_state=contextFile, accept_downloads=True)
            if self.saveTrace:
                self.context.tracing.start(screenshots=True, snapshots=True)
            self.page = self.context.new_page()
            self.page.set_default_timeout(self.timeout)

            return self.login()

        except TimeoutError:
            self.stopTracing()
            raise

    def stopTracing(self):
        if self.saveTrace:
            self.context.tracing.stop(path=self.debugPath / "trace.zip")

    def listAccounts(self):
        try:
            self.logger.debug("List bank accounts")
            url = f"{self.apiUrl}/budget/mouvements"

            if self.page.url != url:
                self.logger.debug(f"Load url {url}")
                self.page.goto(url)

            self.locatorHeaderAccountsPage = self.page.get_by_text("Mes comptes bancaires", exact=True)
            self.locatorHeaderAccountsPage.wait_for(state="visible")

            locatorAccounts = self.page.locator("css=a.c-info-box__link-wrapper")

            locatorAccounts.first.wait_for(state="visible")

            for accountEl in locatorAccounts.all():
                name = (accountEl.get_attribute("title") or "").strip()
                balanceEl = accountEl.locator("css=span.c-info-box__account-balance")
                if balanceEl.count() == 0:
                    # This is not an account (insurrance). Skip
                    continue
                balance = self.cleanAmount(balanceEl.text_content() or "")
                accountLabelEl = accountEl.locator("css=span.c-info-box__account-label")
                if accountLabelEl.count() == 0:
                    # This is not an account (Tous mes comptes). Skip
                    continue
                guid = accountLabelEl.get_attribute("data-account-label")
                if guid is None:
                    # This is not an account (Tous mes comptes). Skip
                    continue
                link = self.apiUrl + (accountEl.get_attribute("href") or "")

                boursoAccount = BoursoAccount(guid, name, balance, link)
                self.logger.debug(f"Account: {boursoAccount}")
                yield boursoAccount
        except TimeoutError:
            self.stopTracing()
            raise

    def saveNewTransactionsForAccount(self, account: BoursoAccount):
        self.logger.info(f"Saving new transactions for account: {account.name}")
        accountTransacPath = self.transactionsPath / account.id
        authorizationPath = accountTransacPath / "authorization"
        oldAuthorizationPath = authorizationPath / "old"
        newAuthorizationPath = authorizationPath / "new"
        newOperationCount = 0
        newPendingOperationCount = 0

        checkExistingCount = 55

        oldAuthorizationPath.mkdir(parents=True, exist_ok=True)
        newAuthorizationPath.mkdir(parents=True, exist_ok=True)
        for newAuthoPath in newAuthorizationPath.glob("*.json"):
            newAuthoPath.rename(oldAuthorizationPath / newAuthoPath.name)

        if not accountTransacPath.exists():
            return
        try:
            listOperationSeenId: set[str] = set()
            listOperationId = {f.stem for f in accountTransacPath.glob("20*/*/*/*.json")}
            listPendingOperationId = {f.stem for f in oldAuthorizationPath.glob("*.json")}

            if self.page.url != account.link:
                self.logger.debug(f"opening transaction details page : {account.link}")
                self.page.goto(account.link)

            countExisting = 0

            nextPageLink = self.page.get_by_role("link", name="Mouvements précédents")
            loadingMessage = self.page.get_by_text("Récupération des mouvements")

            while True:
                # operationCount = len(listOperationId)
                locatorRowTransaction = self.page.locator("css=ul.list__movement > li.list-operation-item")

                for rowEl in locatorRowTransaction.all():
                    labelEl = rowEl.locator(".list-operation-item__label")
                    operationId = rowEl.get_attribute("data-id")
                    if labelEl.count() == 0 or operationId is None:
                        continue
                    if operationId in listOperationSeenId:
                        continue
                    listOperationSeenId.add(operationId)
                    if operationId in listOperationId:
                        countExisting += 1
                        self.logger.debug(
                            f"Operation {operationId} already exists ({countExisting}/{checkExistingCount}), skipping"
                        )

                if countExisting >= checkExistingCount:
                    # Reach expected existing operations count. Stop loading more pages
                    break
                else:
                    if nextPageLink.count() == 0:
                        self.logger.debug("No next page link found")
                        break
                    self.logger.info("Click next page link")
                    time.sleep(0.5)
                    nextPageLink.click()

                    multiLocator = self.orLocator([nextPageLink, loadingMessage])

                    self.logger.info("Wait for loading msg to appear")
                    multiLocator.wait_for(state="visible")
                    self.logger.info("Wait for loading msg to disappear")
                    loadingMessage.wait_for(state="hidden")
                    time.sleep(0.5)
                    self.logger.info("Load next page done")

            # At this point all new transactions are shown on the page.
            # We get the list and reverse it to start from the oldest
            revRowTransactionEls = self.page.query_selector_all("ul.list__movement > li.list-operation-item")[::-1]

            for rowEl in revRowTransactionEls:
                labelEl = rowEl.query_selector(".list-operation-item__label")
                operationId = rowEl.get_attribute("data-id")
                if labelEl is None or operationId is None:
                    continue
                if operationId in listPendingOperationId:
                    # The operation is pending and the file already exist in the old folder.
                    # We move it to the new folder back
                    transactionPath = oldAuthorizationPath / f"{operationId}.json"
                    transactionPath.rename(newAuthorizationPath / transactionPath.name)
                    continue
                elif operationId in listOperationId:
                    # The operation already exist. Skip
                    continue

                # New transaction. Click on the link to trigger the loading of details
                with self.page.expect_response(re.compile(".*operation.*")) as response_info:
                    labelEl.click()
                try:
                    operation = msgspec.json.decode(response_info.value.body(), type=BoursoApiOperation)
                    opDate = operation.getDate()
                    if operation.operation.status.id == "authorization" or "READ_ONLY" in operation.operation.flags:
                        # The operation is an authorization. It goes in the new authorization folder.
                        newPendingOperationCount += 1
                        transactionPath = newAuthorizationPath / f"{operation.operation.id}.json"
                    elif opDate is not None:
                        # A date is found, the transaction is saved into year / month / day hierarchy
                        newOperationCount += 1
                        year, month, day = opDate.split("-")
                        transactionPath = accountTransacPath / year / month / day / f"{operation.operation.id}.json"
                    else:
                        # Unknown date
                        transactionPath = accountTransacPath / "unknown_date" / f"{operation.operation.id}.json"
                except msgspec.ValidationError:
                    # Json cannot be parsed. Save it to invalid folder
                    transactionPath = accountTransacPath / "invalid" / f"{operationId}.json"

                if not transactionPath.exists():
                    # Create the folder is needed
                    transactionPath.parent.mkdir(exist_ok=True, parents=True)
                    self.logger.debug(f"Saving {transactionPath}")
                    # Save the json
                    transactionPath.write_bytes(response_info.value.body())

            self.logger.info(
                f"Retrieve {newOperationCount} new operations and {newPendingOperationCount} new pending operations"
            )
            self.logger.info("No more operation")
        except TimeoutError:
            self.stopTracing()
            raise

    def decryptPassword(self):
        self.page.wait_for_selector("div.sasmap > ul > li > button > img", state="visible")
        time.sleep(1)
        vKeys = self.page.query_selector_all("div.sasmap > ul > li > button > img")

        regexPassword = re.compile(r"data:image\/svg\+xml;base64,\s*(.*)")
        testBatch: list[Button] = []
        for vKey in vKeys:
            src = vKey.get_attribute("src")
            if src is None:
                raise Exception("Button has no attribute src")

            # Extract the base64 representation
            m = regexPassword.match(src)

            if m:
                imgBase64 = m.group(1)
                button = Button(None, imgBase64)
                button.element = vKey
                testBatch.append(button)

        for button in testBatch:
            maxRatio = 0
            bestMatch: Button | None = None

            for referenceImage in referenceButtons:
                similarityRatio = SequenceMatcher(None, referenceImage.svgStr, button.svgStr).ratio()
                if similarityRatio > maxRatio:
                    maxRatio = similarityRatio
                    bestMatch = referenceImage

            if bestMatch is not None:
                button.number = bestMatch.number

        for char in self.password:
            for button in testBatch:
                if char == str(button.number):
                    if button.element is not None:
                        button.element.click()
                    break

    def login(self):
        url = f"{self.apiUrl}/budget/mouvements"
        self.logger.debug(f"Load accounts page : {url}")
        self.page.goto(url)

        self.locatorCookies = self.page.get_by_role("button", name="Continuer sans accepter →")
        self.locatorId = self.page.get_by_role("textbox", name="Saisissez votre identifiant")
        self.locatorMemorize = self.page.get_by_text("Mémoriser mon identifiant")
        self.locatorButtonNext = self.page.get_by_role("button", name="Suivant")
        self.locatorButtonConnect = self.page.get_by_role("button", name="Je me connecte")
        self.locatorButtonReconnect = self.page.get_by_role("link", name="Je me reconnecte")
        self.locatorHeaderAccountsPage = self.page.get_by_text("Mes comptes bancaires", exact=True)
        self.locatorWrongPass = self.page.get_by_text("Identifiant ou mot de passe")

        expectedLocators: list[Locator] = [
            self.locatorCookies,
            self.locatorId,
            self.locatorButtonConnect,
            self.locatorHeaderAccountsPage,
            self.locatorButtonReconnect,
        ]

        while True:
            multiLocator = self.orLocator(expectedLocators)
            multiLocator.wait_for(state="visible")
            if self.locatorCookies in expectedLocators and len(self.locatorCookies.all()) > 0:
                self.logger.debug("Found cookie consent, click no")
                self.locatorCookies.click()
                expectedLocators.remove(self.locatorCookies)
            elif self.locatorHeaderAccountsPage in expectedLocators and len(self.locatorHeaderAccountsPage.all()) > 0:
                self.logger.info("Already connected !")
                return True
            elif self.locatorButtonReconnect in expectedLocators and len(self.locatorButtonReconnect.all()) > 0:
                self.logger.info("Click reconnect button")
                self.locatorButtonReconnect.click()
                expectedLocators.remove(self.locatorButtonReconnect)
            elif self.locatorId in expectedLocators and len(self.locatorId.all()) > 0:
                self.logger.debug("Found username input, enter login")
                self.locatorId.fill(self.username)
                self.locatorMemorize.click()
                self.logger.debug("Clic submit login id")
                self.locatorButtonNext.click()
                expectedLocators.remove(self.locatorId)
            elif self.locatorButtonConnect in expectedLocators and len(self.locatorButtonConnect.all()) > 0:
                self.logger.debug("Found Button connect")
                self.logger.debug("Enter password")
                self.decryptPassword()

                time.sleep(0.3)

                # click on validate button
                self.logger.debug("Clic Connect Button")
                self.locatorButtonConnect.click()
                break

        expectedLocators = [self.locatorHeaderAccountsPage, self.locatorWrongPass]

        multiLocator = self.orLocator(expectedLocators)
        multiLocator.wait_for(state="visible")
        if len(self.locatorHeaderAccountsPage.all()) > 0:
            self.logger.info("Login successfull!")
            self.logger.debug("Saving context")
            self.context.storage_state(path=self.contextFile)
            return True
        elif len(self.locatorWrongPass.all()) > 0:
            self.logger.error("Wrong password!")
        else:
            self.logger.error("Unexpected result, login failed.")
        return False

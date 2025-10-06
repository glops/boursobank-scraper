import logging
import re
import time
from decimal import Decimal
from pathlib import Path

import msgspec
from PIL import ImageChops
from playwright.sync_api import (
    BrowserContext,
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
        self, username: str, password: str, rootDataPath: Path, headless: bool = True
    ):
        self.logger = logging.getLogger(__name__)

        self.apiUrl = "https://clients.boursobank.com"
        self.username = username
        self.password = password
        self.rootDataPath = rootDataPath
        self.debugPath = self.rootDataPath / "debug"
        self.debugPath.mkdir(exist_ok=True)
        self.transactionsPath = self.rootDataPath / "transactions"
        self.transactionsPath.mkdir(exist_ok=True)

        self.regexCleanAmount = re.compile(r"[^0-9,-]+", flags=re.I)

        self.contextFile = self.debugPath / "context.json"

        self.logger.debug("Start playwright and chromium")
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=headless)
        self.context: BrowserContext
        self.page: Page

    def close(self):
        self.logger.debug("Close browser and stop playwright")
        self.browser.close()
        self.playwright.stop()

    def cleanAmount(self, amountStr: str) -> Decimal:
        balanceClean = self.regexCleanAmount.sub("", amountStr).replace(",", ".")

        return Decimal(balanceClean).quantize(Decimal("1.00"))

    def connect(self) -> bool:
        try:
            ######################################
            ######## Login page ##################
            ######################################

            if self.contextFile.is_file():
                self.logger.debug("Login state exists. Load it")
                self.context = self.browser.new_context(
                    storage_state=self.contextFile, accept_downloads=True
                )
                self.context.tracing.start(screenshots=True, snapshots=True)
                self.page = self.context.new_page()
                self.page.set_default_timeout(30000)
                url = f"{self.apiUrl}/budget/mouvements"
                self.logger.debug(f"Load accounts page : {url}")
                self.page.goto(url)

                try:
                    self.page.wait_for_selector(
                        "a.c-info-box__link-wrapper", timeout=4000
                    )
                    self.logger.debug("Logged in successfully")
                    return True
                except TimeoutError:
                    self.logger.debug("Not connected. State must be too old.")
                    self.contextFile.unlink(missing_ok=True)
                    return self.login()
            else:
                self.logger.debug("No state file exists. Try to login.")
                self.context = self.browser.new_context(accept_downloads=True)
                self.context.tracing.start(screenshots=True, snapshots=True)
                self.page = self.context.new_page()
                self.page.set_default_timeout(30000)
                return self.login()
        except TimeoutError:
            self.stopTracing()

            self.page.screenshot(path=self.debugPath / "timeouterror.png")
            raise

    def stopTracing(self):
        self.context.tracing.stop(path=self.debugPath / "timeouterror_trace.zip")

    def listAccounts(self):
        try:
            self.logger.debug("List bank accounts")
            url = f"{self.apiUrl}/budget/mouvements"
            if self.page.url != url:
                self.logger.debug(f"Load url {url}")
                self.page.goto(url)

            self.page.wait_for_selector("a.c-info-box__link-wrapper")

            accountEls = self.page.query_selector_all("a.c-info-box__link-wrapper")

            for accountEl in accountEls:
                name = (accountEl.get_attribute("title") or "").strip()
                balanceEl = accountEl.query_selector("span.c-info-box__account-balance")
                if balanceEl is None:
                    # This is not an account (insurrance). Skip
                    continue
                balance = self.cleanAmount(balanceEl.text_content() or "")
                accountLabelEl = accountEl.query_selector(
                    "span.c-info-box__account-label"
                )
                if accountLabelEl is None:
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
            self.context.tracing.stop(path=self.debugPath / "timeouterror_trace.zip")

            self.page.screenshot(path=self.debugPath / "timeouterror.png")
            raise

    def saveNewTransactionsForAccount(self, account: BoursoAccount):
        self.logger.info(f"Saving new transactions for account: {account.name}")
        accountTransacPath = self.transactionsPath / account.id
        authorizationPath = accountTransacPath / "authorization"
        oldAuthorizationPath = authorizationPath / "old"
        newAuthorizationPath = authorizationPath / "new"
        newOperationCount = 0
        newPendingOperationCount = 0

        oldAuthorizationPath.mkdir(parents=True, exist_ok=True)
        newAuthorizationPath.mkdir(parents=True, exist_ok=True)
        for newAuthoPath in newAuthorizationPath.glob("*.json"):
            newAuthoPath.rename(oldAuthorizationPath / newAuthoPath.name)

        if not accountTransacPath.exists():
            return
        try:
            listOperationSeenId: set[str] = set()
            listOperationId = {
                f.stem for f in accountTransacPath.glob("20*/*/*/*.json")
            }
            listPendingOperationId = {
                f.stem for f in oldAuthorizationPath.glob("*.json")
            }

            if self.page.url != account.link:
                self.logger.debug(f"opening transaction details page : {account.link}")
                self.page.goto(account.link)

            countExisting = 0

            while True:
                operationCount = len(listOperationId)
                rowTransactionEls = self.page.query_selector_all(
                    "ul.list__movement > li.list-operation-item"
                )

                for rowEl in rowTransactionEls:
                    labelEl = rowEl.query_selector(".list-operation-item__label")
                    operationId = rowEl.get_attribute("data-id")
                    if labelEl is None or operationId is None:
                        continue
                    if operationId in listOperationSeenId:
                        continue
                    listOperationSeenId.add(operationId)
                    if operationId in listPendingOperationId:
                        # The operation is pending and the file already exist in the old folder
                        transactionPath = oldAuthorizationPath / f"{operationId}.json"
                        transactionPath.rename(
                            newAuthorizationPath / transactionPath.name
                        )
                    elif operationId not in listOperationId:
                        listOperationId.add(operationId)

                        with self.page.expect_response(
                            re.compile(".*operation.*")
                        ) as response_info:
                            labelEl.click()
                        try:
                            operation = msgspec.json.decode(
                                response_info.value.body(), type=BoursoApiOperation
                            )
                            opDate = operation.getDate()
                            if (
                                operation.operation.status.id == "authorization"
                                or "READ_ONLY" in operation.operation.flags
                            ):
                                newPendingOperationCount += 1
                                transactionPath = (
                                    newAuthorizationPath
                                    / f"{operation.operation.id}.json"
                                )
                            elif opDate is not None:
                                newOperationCount += 1
                                year, month, day = opDate.split("-")
                                transactionPath = (
                                    accountTransacPath
                                    / year
                                    / month
                                    / day
                                    / f"{operation.operation.id}.json"
                                )
                            else:
                                transactionPath = (
                                    accountTransacPath
                                    / "unknown_date"
                                    / f"{operation.operation.id}.json"
                                )
                        except msgspec.ValidationError:
                            transactionPath = (
                                accountTransacPath / "invalid" / f"{operationId}.json"
                            )

                        if not transactionPath.exists():
                            transactionPath.parent.mkdir(exist_ok=True, parents=True)
                            self.logger.debug(f"Saving {transactionPath}")
                            transactionPath.write_bytes(response_info.value.body())
                    elif operationId in listOperationId:
                        self.logger.debug(
                            f"Operation {operationId} already exists, skipping"
                        )
                        countExisting += 1

                if operationCount == len(listOperationId) or countExisting > 50:
                    # If no more operation has been found, stop.
                    break
                else:
                    nextPageLink = self.page.query_selector(
                        "li.list__movement__range-summary > a"
                    )
                    if nextPageLink is None:
                        self.logger.debug("No next page link found")
                        break
                    self.logger.info("Click next page link")
                    nextPageLink.click()
                    time.sleep(1)
                    nextPageLink = self.page.query_selector(
                        "li.list__movement__range-summary > a"
                    )
                    self.logger.info("Load done")

            self.logger.info(
                f"Retrieve {newOperationCount} new operations and {newPendingOperationCount} new pending operations"
            )
            self.logger.info("No more operation")
        except TimeoutError:
            self.context.tracing.stop(path=self.debugPath / "timeouterror_trace.zip")

            self.page.screenshot(path=self.debugPath / "timeouterror.png")
            raise

    def decryptPassword(self):
        self.page.wait_for_selector(
            "div.sasmap > ul > li > button > img", state="visible"
        )
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
            button.image
            minDiff = 99999999
            bestMatch: Button | None = None

            for referenceImage in referenceButtons:
                diff = ImageChops.difference(referenceImage.image, button.image)

                totalDiff = 0
                for x in range(0, diff.width):
                    for y in range(0, diff.height):
                        pixel = diff.getpixel((x, y))
                        if isinstance(pixel, tuple):
                            totalDiff += pixel[0] + pixel[1] + pixel[2]
                if totalDiff < minDiff:
                    minDiff = totalDiff
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
        url = f"{self.apiUrl}/connexion/"
        if self.page.url != url:
            self.logger.debug(f"Loading {url}")
            self.page.goto(url)

        try:
            # If there is a privacy popup, close it
            self.page.click(".didomi-continue-without-agreeing", timeout=5000)
            self.logger.debug("Clicked on privacy validation button")
        except TimeoutError:
            pass

        self.page.type("input#form_clientNumber", self.username)

        self.page.screenshot(path=self.debugPath / "loginpage.png")

        self.logger.debug("Clic submit login id")
        self.page.click("button[data-login-id-submit]")
        self.page.wait_for_selector(
            "div.sasmap > ul > li > button > img", state="visible"
        )
        self.decryptPassword()

        time.sleep(2)
        self.page.screenshot(path=self.debugPath / "passwordpage.png")

        # click on validate button
        self.logger.debug("Clic submit password")
        self.page.click("button[data-login-submit]")
        time.sleep(3)

        # Wait for an element to appear
        # TODO: This selector is not always found
        self.logger.debug("Logged in successfully")
        self.logger.debug("Saving context")
        self.context.storage_state(path=self.contextFile)

        return True

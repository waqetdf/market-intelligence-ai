"""Market Intelligence AI native window and local application lifecycle."""

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import secrets
import sys
from tempfile import TemporaryDirectory

from dotenv import load_dotenv
from PySide6.QtCore import QLockFile, QStandardPaths, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineUrlRequestInterceptor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

from backend.desktop_runtime import DesktopRuntime, TOKEN_HEADER


def is_local(url, port):
    return url.scheme() == "http" and url.host() == "127.0.0.1" and url.port() == port


class PrivateRequests(QWebEngineUrlRequestInterceptor):
    def __init__(self, port, token, parent):
        super().__init__(parent)
        self.port = port
        self.token = token

    def interceptRequest(self, info):
        if is_local(info.requestUrl(), self.port):
            info.setHttpHeader(TOKEN_HEADER, self.token)
        else:
            info.block(True)


class DashboardPage(QWebEnginePage):
    def __init__(self, profile, port, parent):
        super().__init__(profile, parent)
        self.port = port
        self.newWindowRequested.connect(lambda request: self.open_link(request.requestedUrl()))

    def open_link(self, url):
        if is_local(url, self.port):
            self.setUrl(url)
        elif url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)

    def acceptNavigationRequest(self, url, kind, is_main_frame):
        if is_local(url, self.port):
            return True
        if is_main_frame and kind == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            self.open_link(url)
        return False


def show_dashboard(gui, directory, runtime, token, smoke_test):
    window = QMainWindow()
    window.setWindowTitle("Market Intelligence AI")
    window.resize(1350, 900)
    profile = QWebEngineProfile(window)
    interceptor = PrivateRequests(runtime.port, token, profile)
    profile.setUrlRequestInterceptor(interceptor)
    view = QWebEngineView(window)
    page = DashboardPage(profile, runtime.port, view)
    view.setPage(page)
    window.setCentralWidget(view)
    menu = window.menuBar().addMenu("Archivo")
    action = menu.addAction("Abrir carpeta de datos")
    action.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory))))
    menu.addAction("Salir", gui.quit)
    page.load(QUrl(f"http://127.0.0.1:{runtime.port}/"))
    window.show()
    if smoke_test:
        timer = QTimer(window)

        def report(value):
            if value == "Observatorio de mercados":
                timer.stop()
                gui.exit(0)

        timer.timeout.connect(lambda: page.runJavaScript("document.querySelector('h1')?.textContent", report))
        timer.start(250)
        QTimer.singleShot(15000, lambda: gui.exit(1))
    try:
        return gui.exec()
    finally:
        from shiboken6 import delete

        delete(view)  # The page must be destroyed before its profile.
        delete(window)


def main():
    smoke_test = "--smoke-test" in sys.argv
    gui = QApplication([])
    gui.setApplicationName("Market Intelligence AI")
    gui.setOrganizationName("Market Intelligence AI")
    temporary = TemporaryDirectory(prefix="market-desktop-") if smoke_test else None
    directory = Path(temporary.name if temporary else QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppLocalDataLocation))
    lock = QLockFile(str(directory / "desktop.lock"))
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not lock.tryLock(0):
            QMessageBox.information(None, "Market Intelligence AI", "La aplicación ya está abierta.")
            return 1
        frontend = Path(__file__).resolve().parent / "frontend" / "dist"
        if not (frontend / "index.html").is_file():
            raise RuntimeError("Falta compilar el panel. Consulta la guía de escritorio.")
        load_dotenv(directory / ".env")
        os.environ.setdefault("MARKET_NEWS_FEEDS",
                              "https://www.federalreserve.gov/feeds/press_monetary.xml,"
                              "https://www.ecb.europa.eu/rss/press.html")
        os.environ["MARKET_DATA_DIR"] = str(directory)
        os.environ["MARKET_FRONTEND_DIR"] = str(frontend)
        for key in ("DATABASE_URL", "MARKET_PASSWORD", "MARKET_REQUIRE_AUTH", "MARKET_DASHBOARD_URL"):
            os.environ.pop(key, None)
        (directory / "mt5").mkdir(exist_ok=True)
        logging.basicConfig(level=logging.INFO, handlers=[
            RotatingFileHandler(directory / "desktop.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        ])
        from backend.app import app

        token = secrets.token_hex(32).encode("ascii")
        with DesktopRuntime(app, token) as runtime:
            return show_dashboard(gui, directory, runtime, token, smoke_test)
    except (OSError, RuntimeError) as exc:
        if not smoke_test:
            QMessageBox.critical(None, "Market Intelligence AI", str(exc))
        return 1
    finally:
        lock.unlock()
        if temporary:
            logging.shutdown()
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())

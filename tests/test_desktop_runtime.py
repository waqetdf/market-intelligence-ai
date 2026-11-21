from fastapi import FastAPI
import httpx

from backend.desktop_runtime import DesktopRuntime


def test_desktop_transport_requires_window_token_and_closes_cleanly():
    app = FastAPI()

    @app.get("/")
    def home():
        return {"desktop": True}

    with DesktopRuntime(app, b"test-secret") as runtime:
        endpoint = f"http://127.0.0.1:{runtime.port}/"
        with httpx.Client(trust_env=False) as client:
            assert client.get(endpoint).status_code == 403
            assert client.get(endpoint, headers={"x-market-desktop-token": "wrong"}).status_code == 403
            response = client.get(endpoint, headers={"x-market-desktop-token": "test-secret"})
            assert response.json() == {"desktop": True}
    assert not runtime.thread.is_alive()

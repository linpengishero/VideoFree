import threading
import time
import urllib.request
import webbrowser

import uvicorn

from .bootstrap import context


URL = f"http://127.0.0.1:{context.config.port}/"


def open_browser_when_ready() -> None:
    for _ in range(120):
        try:
            with urllib.request.urlopen(URL, timeout=1):
                webbrowser.open(URL)
                return
        except OSError:
            time.sleep(0.5)


if __name__ == "__main__":
    if context.config.host not in {"127.0.0.1", "localhost", "::1"} and not context.config.api_token:
        print("[WARNING] Gateway is exposed beyond localhost without MEDIA_GATEWAY_TOKEN.")
    threading.Thread(target=open_browser_when_ready, daemon=True).start()
    uvicorn.run("backend.main:app", host=context.config.host, port=context.config.port)

# Copyright (c) 2026 VideoFree Studio individual project author and contributors.
# Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

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
    threading.Thread(target=open_browser_when_ready, daemon=True).start()
    uvicorn.run("backend.main:app", host=context.config.host, port=context.config.port)

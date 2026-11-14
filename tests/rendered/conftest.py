#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 16:56:38.227152
Revised: 2026/11/14 18:33:18.470323

The rendered tests' app: the driver process (``driver.py``) started once on a scratch data folder, and what a
test does with it: ask it where a widget is, click and drag there with posted window messages, read what the
window shows with PrintWindow, and ask for the state the click left.
"""

import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from PyQt6.QtGui import QColor, QImage

ANSWER_SECONDS = 30.0
SETTLE_SECONDS = 0.25
"""After the app says it is idle: the time a repaint takes to reach the window."""
ROOT = Path(__file__).parents[2]


class DriverFailed(Exception):
    pass


class App:
    def __init__(self, data: Path) -> None:
        from tests.rendered import window  # Windows only: the tests skip elsewhere before an App is made

        self._window = window
        self._errors = (data / "driver.log").open("w+", encoding="utf-8")
        self._process = subprocess.Popen(
            [sys.executable, "-m", "tests.rendered.driver", str(data)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._errors,
            text=True,
            encoding="utf-8",
            cwd=ROOT,
        )
        self._answers: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        try:
            self._answer()  # it says when its windows are up
        except BaseException:
            self._process.kill()  # never leave a test copy running, its windows on the screen
            self._errors.close()
            raise

    def _read(self) -> None:
        for line in self._process.stdout:
            if line.startswith("@@"):
                self._answers.put(line[2:])
        self._answers.put(None)

    def _said(self) -> str:
        self._errors.flush()
        self._errors.seek(0)
        return self._errors.read()[-3000:]

    def _answer(self) -> dict:
        try:
            line = self._answers.get(timeout=ANSWER_SECONDS)
        except queue.Empty:
            raise DriverFailed(f"the driver didn't answer in {ANSWER_SECONDS:.0f} s:\n{self._said()}") from None
        if line is None:
            raise DriverFailed(f"the driver ended:\n{self._said()}")
        answer = json.loads(line)
        if not answer.pop("ok"):
            raise DriverFailed(f"{answer['error']}\n{self._said()}")
        return answer

    def ask(self, do: str, **more) -> dict:
        self._process.stdin.write(json.dumps({"do": do, **more}) + "\n")
        self._process.stdin.flush()
        return self._answer()

    # --- what a test does -----------------------------------------------------------------------------------

    def start(self, language: str = "English", fresh: bool = True) -> None:
        """Start the app over: as on a first start, or (``fresh=False``) with what the last run saved."""
        if fresh:
            self.ask("wipe")
        self.ask("restart", language=language)
        self.settle()

    def state(self) -> dict:
        return self.ask("state")

    def settle(self) -> dict:
        """Wait for the app's background work, then for the repaint; the state it is left in."""
        state = self.until(lambda state: not state["busy"])
        time.sleep(SETTLE_SECONDS)
        return state

    def until(self, holds, timeout: float = 5.0) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            state = self.state()
            if holds(state):
                return state
            if time.monotonic() > deadline:
                raise AssertionError(f"still waiting after {timeout:.0f} s; the app's state: {state}")
            time.sleep(0.05)

    def where(self, part: str) -> tuple[int, int, int, int, int]:
        """The window's handle and the part's left, top, width and height in it."""
        found = self.ask("where", part=part)
        return (found["hwnd"], *found["rect"])

    def click(self, part: str, at: tuple[float, float] = (0.5, 0.5), right: bool = False) -> None:
        """Click ``part``, by default in its middle (``at`` is the share of its width and height)."""
        hwnd, left, top, width, height = self.where(part)
        self._window.click(hwnd, left + int((width - 1) * at[0]), top + int((height - 1) * at[1]), right=right)
        self.settle()

    def drag(self, part: str, *points: tuple[int, int]) -> None:
        """Drag over ``part`` through ``points``, counted from its top left corner."""
        hwnd, left, top, _, _ = self.where(part)
        self._window.drag(hwnd, *[(left + x, top + y) for x, y in points])
        self.settle()

    def type(self, part: str, text: str) -> None:
        """Click ``part`` and type ``text`` into it."""
        self.click(part)
        self._window.type_text(self.where(part)[0], text)
        self.settle()

    def shot(self, part: str) -> QImage:
        """What the window holding ``part`` shows now, cut to ``part``."""
        hwnd, left, top, width, height = self.where(part)
        return self._window.capture(hwnd).copy(left, top, width, height)

    def pixel(self, part: str, x: int, y: int) -> QColor:
        return self.shot(part).pixelColor(x, y)

    def ratio(self) -> float:
        return self.ask("where", part="toolbar")["ratio"]

    def quit(self) -> int:
        try:
            self.ask("quit")
            return self._process.wait(15)
        finally:
            if self._process.poll() is None:
                self._process.kill()  # never leave a test copy running
            self._errors.close()


@pytest.fixture(scope="session")
def running(tmp_path_factory):
    """The driver, for the whole run; it must end by itself when told to quit."""
    app = App(tmp_path_factory.mktemp("rendered"))
    yield app
    assert app.quit() == 0


@pytest.fixture
def app(running):
    """The app as on a first start, in English."""
    running.start()
    return running

#!/usr/bin/env python3
"""
Authors: Ran# <ran.hash@proton.me>
Created: 2026/11/14 00:23:10.171960
Revised: 2026/11/14 17:53:24.808607

One Vitralis per Windows account: two would mean two overlays, two sets of global hooks and two writers of the
same files. The first one listens on a local socket named after the account; a second start finds it, asks it
to show its toolbar and quits. While it runs, Vitralis also holds a named Windows mutex (``mark_running``),
which the uninstaller looks for: uninstalling under a running Vitralis would leave its exe behind. The mutex
also settles two starts at the same moment, when neither is listening yet for the other to find: Windows makes
it for one of them only, and the other quits.
"""

import ctypes
import getpass
import logging
from dataclasses import dataclass

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

logger = logging.getLogger("vitralis.single_instance")

CONNECT_TIMEOUT_MS = 500
RUNNING_MUTEX = "VitralisRunning"
"""The mutex's name; ``installer/vitralis.iss`` names the same one (``AppMutex``)."""
ERROR_ALREADY_EXISTS = 183
"""What Windows says when the mutex asked for was already there: the handle it gives is to that one."""


@dataclass(frozen=True, slots=True)
class RunningMark:
    handle: int
    first: bool
    """Whether this process made the mutex; ``False`` when another Vitralis already held it."""


def mark_running(name: str = RUNNING_MUTEX) -> RunningMark | None:
    """Hold the mutex ``name`` until the process ends (Windows frees it then, however Vitralis quits), and say
    whether this process is the first to hold it. ``None`` when it couldn't be made, which is logged: the
    uninstaller's question and the guard against two starts at once are lost, nothing else."""
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        handle = kernel32.CreateMutexW(None, False, name)
        error = ctypes.get_last_error()
    except (AttributeError, OSError) as ex:  # not Windows
        logger.warning("couldn't mark Vitralis as running: %s", ex)
        return None
    if not handle:
        logger.warning("couldn't mark Vitralis as running (error %d)", error)
        return None
    return RunningMark(handle, first=error != ERROR_ALREADY_EXISTS)


def default_name() -> str:
    """The socket's name: one per account, since a local socket is seen by every account on the computer."""
    try:
        user = getpass.getuser()
    except (OSError, KeyError, ImportError) as ex:
        logger.warning("couldn't tell the account's name: %s", ex)
        user = "user"
    return f"vitralis-{user}"


class SingleInstance(QObject):
    activated = pyqtSignal()
    """Another start of Vitralis asked this one to show itself."""

    def __init__(self, name: str | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._name = name or default_name()
        self._server: QLocalServer | None = None

    def notify_running(self) -> bool:
        """Whether a Vitralis is already running; it is asked to show its toolbar."""
        socket = QLocalSocket()
        socket.connectToServer(self._name)
        if not socket.waitForConnected(CONNECT_TIMEOUT_MS):
            return False
        socket.disconnectFromServer()  # the connection is the whole message; it waits for the other's event loop
        return True

    def listen(self) -> bool:
        """Become the running Vitralis; whether listening worked (a failure is logged, the app still runs)."""
        server = QLocalServer(self)
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        server.newConnection.connect(self._on_connection)
        if not server.listen(self._name):
            logger.warning("couldn't listen for other starts of Vitralis on %s: %s", self._name, server.errorString())
            server.deleteLater()
            return False
        self._server = server
        return True

    def close(self) -> None:
        """Stop listening. Safe to call twice."""
        if self._server is not None:
            self._server.close()
            self._server.deleteLater()
            self._server = None

    def _on_connection(self) -> None:
        while self._server is not None and self._server.hasPendingConnections():
            connection = self._server.nextPendingConnection()
            connection.disconnected.connect(connection.deleteLater)
            logger.info("another start of Vitralis asked this one to show itself")
            self.activated.emit()

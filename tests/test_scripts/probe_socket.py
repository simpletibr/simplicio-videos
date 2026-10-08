"""Probe run by test_socket_guard.py in a nested pytest (the name is not collected by default)."""
import socket

import pytest


def test_unit_cannot_open_a_socket():
    socket.socket(socket.AF_INET, socket.SOCK_STREAM)


def test_unit_may_use_a_unix_socketpair():
    a, b = socket.socketpair()
    a.close()
    b.close()


@pytest.mark.render
def test_render_may_open_a_socket():
    socket.socket(socket.AF_INET, socket.SOCK_STREAM).close()

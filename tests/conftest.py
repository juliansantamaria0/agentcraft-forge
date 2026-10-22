import importlib
import socket
import sys

import pytest

from agentcraft_forge.generator import generate
from agentcraft_forge.planner import design
from agentcraft_forge.schema import Kind


@pytest.fixture
def runtime_project(tmp_path, monkeypatch):
    def load(kind):
        target = generate(
            design(
                "runtime-" + kind, "Pruebas locales con datos sintéticos", Kind(kind)
            ),
            tmp_path,
        )
        monkeypatch.syspath_prepend(str(target / "src"))
        return target, lambda name: importlib.import_module("agent_app." + name)

    yield load
    for name in list(sys.modules):
        if name == "agent_app" or name.startswith("agent_app."):
            del sys.modules[name]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Las pruebas del generador no deben abrir conexiones.")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)

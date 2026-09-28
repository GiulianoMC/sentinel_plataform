"""
Carregamento de módulos "reais" em testes.

O conftest substitui módulos pesados (SemanticSearchService, LLMService,
app.celery.*) por mocks em sys.modules para que a API possa ser importada sem
chromadb/sentence-transformers. Alguns testes precisam da implementação real —
este helper carrega o ficheiro diretamente, instalando stubs das dependências
externas só durante o import.
"""

import importlib.util
import sys
import types
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_real_module(module_name: str, relative_path: str, stubs=None, package=None):
    """Importa `relative_path` como um módulo novo, sem passar pelos mocks do conftest.

    `stubs` é um dict {nome_do_modulo: modulo} instalado temporariamente em
    sys.modules durante o import (ex: um 'openai' falso quando o SDK instalado
    é antigo demais).
    """
    stubs = stubs or {}
    saved = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location(module_name, PROJECT_ROOT / relative_path)
        module = importlib.util.module_from_spec(spec)
        if package:
            module.__package__ = package
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


def make_openai_stub():
    """Stub mínimo do SDK da OpenAI v1 (o venv local pode ter a 0.x)."""
    stub = types.ModuleType("openai")

    class OpenAI:
        def __init__(self, *args, **kwargs):
            self.chat = None

    class APIError(Exception):
        pass

    class RateLimitError(APIError):
        pass

    class APIConnectionError(APIError):
        pass

    class APITimeoutError(APIConnectionError):
        pass

    stub.OpenAI = OpenAI
    stub.APIError = APIError
    stub.RateLimitError = RateLimitError
    stub.APIConnectionError = APIConnectionError
    stub.APITimeoutError = APITimeoutError
    return stub


def make_chromadb_stub():
    """Stub mínimo do chromadb (o sqlite3 local pode ser antigo demais para o real)."""
    chromadb = types.ModuleType("chromadb")
    utils = types.ModuleType("chromadb.utils")
    config = types.ModuleType("chromadb.config")

    class _EmbeddingFunctions:
        @staticmethod
        def SentenceTransformerEmbeddingFunction(model_name=None):
            raise NotImplementedError("stub: o teste não deve construir o serviço")

    chromadb.Client = lambda *a, **k: None
    utils.embedding_functions = _EmbeddingFunctions
    config.Settings = lambda *a, **k: None
    chromadb.utils = utils
    chromadb.config = config
    return {"chromadb": chromadb, "chromadb.utils": utils, "chromadb.config": config}


class FakeRetry(Exception):
    """Equivalente a celery.exceptions.Retry para os testes."""

    def __init__(self, exc=None, countdown=None):
        super().__init__(f"retry(countdown={countdown})")
        self.exc = exc
        self.countdown = countdown


class FakeTaskSelf:
    """`self` das tasks declaradas com bind=True."""

    def retry(self, exc=None, countdown=None, **kwargs):
        # As tasks fazem `raise self.retry(...)`, então basta devolver a excepção.
        return FakeRetry(exc=exc, countdown=countdown)


def make_celery_stub():
    """Stub de app.celery.celery_app cujo decorador @celery.task devolve a função real.

    Com o MagicMock do conftest, a task decorada vira um MagicMock e o corpo nunca
    executa — este stub permite chamar a task diretamente no teste.
    """
    from unittest.mock import MagicMock

    module = types.ModuleType("app.celery.celery_app")

    class _Celery:
        def __init__(self):
            self.send_task = MagicMock()
            self.conf = MagicMock()

        def task(self, *dargs, **dkwargs):
            bind = dkwargs.get("bind", False)

            def wrap(fn):
                def call(*args, **kwargs):
                    return fn(FakeTaskSelf(), *args, **kwargs) if bind else fn(*args, **kwargs)

                call.fn = fn
                call.delay = MagicMock()
                call.apply_async = MagicMock()
                return call

            # Suporta tanto @celery.task quanto @celery.task(...)
            if len(dargs) == 1 and callable(dargs[0]) and not dkwargs:
                return wrap(dargs[0])
            return wrap

    module.celery = _Celery()
    return {"app.celery.celery_app": module}

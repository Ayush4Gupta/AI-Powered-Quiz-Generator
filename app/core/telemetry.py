# telemetry.py
from prometheus_fastapi_instrumentator import Instrumentator
from fastapi import FastAPI

def init_telemetry(app: FastAPI) -> None:
    Instrumentator().instrument(app).expose(app)

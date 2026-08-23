"""Flask application factory. Routes and templates are fleshed out at milestone M6."""
from __future__ import annotations

from flask import Flask

from .config import Config
from .db import init_engine


def create_app(config: type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config)

    init_engine(app.config["DATABASE_URL"], create_all=True)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/")
    def index():
        return "Document Collection — scaffold OK (UI arrives at M6)"

    return app

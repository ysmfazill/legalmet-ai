"""METRASIGHT — API service (FastAPI).

Package layout::

    app/
      core/       configuration, logging, security, errors, enums
      db/         SQLAlchemy base, session, bootstrap, seed
      models/     ORM models (the Evidence Graph lives here)
      schemas/    Pydantic request/response contracts (camelCase JSON)
      services/   domain + AI service interfaces and (mock) implementations
      api/        HTTP routers and dependencies
      main.py     application factory + middleware + exception handlers
"""

__version__ = "0.1.0"

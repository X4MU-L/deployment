"""Import all models so Alembic auto-detects them."""

from app.db.models.build import Build  # noqa: F401
from app.db.models.deployment import Deployment  # noqa: F401
from app.db.models.environment import Environment  # noqa: F401
from app.db.models.log import LogLine  # noqa: F401
from app.db.models.project import Project  # noqa: F401
from app.db.models.release import Release, Route  # noqa: F401
from app.db.models.user import User  # noqa: F401
"""ORM models. Import all here so Alembic autogenerate sees them."""
from app.models.category import Category
from app.models.portal import Portal
from app.models.ticket import Ticket
from app.models.user import User

__all__ = ["User", "Category", "Portal", "Ticket"]

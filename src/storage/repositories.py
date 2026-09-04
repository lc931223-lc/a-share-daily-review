from sqlalchemy import select
from sqlalchemy.orm import Session

from src.storage.models import Theme, ThemeAlias


def get_or_create_theme(session: Session, canonical_name: str) -> Theme:
    theme = session.scalar(select(Theme).where(Theme.canonical_name == canonical_name))
    if theme is None:
        theme = Theme(canonical_name=canonical_name)
        session.add(theme)
        session.flush()
    return theme


def resolve_theme(session: Session, name: str) -> Theme | None:
    theme = session.scalar(select(Theme).where(Theme.canonical_name == name))
    if theme is not None:
        return theme
    alias = session.scalar(select(ThemeAlias).where(ThemeAlias.alias == name))
    return session.get(Theme, alias.theme_id) if alias else None

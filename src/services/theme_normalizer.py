from sqlalchemy.orm import Session

from src.storage.models import ThemeAlias
from src.storage.repositories import get_or_create_theme, resolve_theme


KNOWN_ALIASES = {}


def normalize_theme(session: Session, name: str):
    canonical_name = KNOWN_ALIASES.get(name, name).strip()
    theme = resolve_theme(session, canonical_name) or get_or_create_theme(session, canonical_name)
    aliases = {alias for alias, canonical in KNOWN_ALIASES.items() if canonical == canonical_name}
    for alias in aliases:
        if resolve_theme(session, alias) is None:
            session.add(ThemeAlias(alias=alias, theme_id=theme.id))
    session.flush()
    return theme

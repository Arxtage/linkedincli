from __future__ import annotations

import re
from collections.abc import Iterable

from linkedincli.models import PageIdentity


def slugify_alias(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or "page"



def assign_page_aliases(pages: Iterable[PageIdentity]) -> list[PageIdentity]:
    assigned: list[PageIdentity] = []
    used: set[str] = set()
    for page in pages:
        base_alias = slugify_alias(page.alias or page.slug or page.name)
        alias = base_alias
        suffix = 2
        while alias in used:
            alias = f"{base_alias}-{suffix}"
            suffix += 1
        used.add(alias)
        assigned.append(
            PageIdentity(
                alias=alias,
                name=page.name,
                slug=page.slug,
                admin_url=page.admin_url,
                public_url=page.public_url,
                entity_urn=page.entity_urn,
            )
        )
    return assigned

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class MemberIdentity:
    name: str
    public_identifier: str
    plain_id: int | None = None
    profile_urn: str | None = None
    headline: str | None = None

    @property
    def profile_url(self) -> str:
        return f"https://www.linkedin.com/in/{self.public_identifier}/"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class PageIdentity:
    alias: str
    name: str
    slug: str
    admin_url: str
    public_url: str
    entity_urn: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> PageIdentity:
        return cls(
            alias=payload["alias"],
            name=payload["name"],
            slug=payload["slug"],
            admin_url=payload["admin_url"],
            public_url=payload["public_url"],
            entity_urn=payload.get("entity_urn"),
        )

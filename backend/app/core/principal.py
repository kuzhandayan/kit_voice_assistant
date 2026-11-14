from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Role(StrEnum):
    PUBLIC = "public"
    STUDENT = "student"
    TEACHER = "teacher"


class Programme(StrEnum):
    UG = "UG"
    PG = "PG"


@dataclass(frozen=True)
class Principal:
    role: Role
    owner_key: str
    user_id: int | None = None
    login_id: str | None = None
    name: str | None = None
    college_token: str | None = field(default=None, repr=False)
    profile: dict[str, Any] = field(default_factory=dict)

    @property
    def is_authenticated(self) -> bool:
        return self.role is not Role.PUBLIC

    @property
    def programme(self) -> Programme:
        raw = str(self.profile.get("programme") or "").upper().replace(".", "")
        return Programme.PG if ("MTECH" in raw or raw == "PG") else Programme.UG

    def public_view(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "user_id": self.user_id,
            "login_id": self.login_id,
            "name": self.name,
            "profile": self.profile,
        }


def role_from_college(value: str) -> Role | None:
    raw = (value or "").lower()
    if "student" in raw:
        return Role.STUDENT
    if "teach" in raw or "faculty" in raw or "staff" in raw:
        return Role.TEACHER
    return None


def public_principal(visitor_id: str) -> Principal:
    return Principal(role=Role.PUBLIC, owner_key=f"visitor:{visitor_id}")

from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass(frozen=True)
class User:
    uid: str
    cn: str
    sn: str
    mail: str
    password: str
    groups: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Group:
    name: str


@dataclass(frozen=True)
class Config:
    users: list[User]
    groups: list[Group]


def load_config(path: Path) -> Config:
    data = yaml.safe_load(path.read_text())
    users = [User(**u) for u in data.get("users", [])]
    groups = [Group(name=g) for g in data.get("groups", [])]
    return Config(users=users, groups=groups)

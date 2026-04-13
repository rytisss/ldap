# OpenLDAP + Keycloak Sandbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible local sandbox where OpenLDAP is the authoritative user directory and Keycloak federates it in `READ_WRITE` mode, with a Python seed container that bootstraps everything from declarative config.

**Architecture:** Four services in one `docker-compose.yml` — `openldap`, `postgres`, `keycloak`, and a one-shot `seed` container. The seed container runs a Python script that upserts LDAP entries from `users.yaml` and configures the Keycloak realm + LDAP federation via the Admin REST API. Pytest in the same container verifies the end-to-end setup.

**Tech Stack:** Docker Compose, osixia/openldap, Keycloak 24, Postgres 16, Python 3.12, `ldap3`, `python-keycloak`, `pyyaml`, `pytest`, `tenacity` (retries).

---

## File Structure

```
ldap/
├── docker-compose.yml          # 4 services on one network
├── .env.example                # default admin creds, DN, ports
├── ldap/
│   └── bootstrap.ldif          # ou=people, ou=groups
├── seed/
│   ├── Dockerfile              # python:3.12-slim + deps
│   ├── pyproject.toml          # project + deps
│   ├── users.yaml              # declarative users/groups
│   ├── seed/
│   │   ├── __init__.py
│   │   ├── config.py           # YAML loader + dataclasses
│   │   ├── ldap_ops.py         # connect, upsert user/group
│   │   ├── keycloak_ops.py     # realm + LDAP federation
│   │   └── main.py             # entrypoint, retries, wiring
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py         # shared fixtures
│       ├── test_config.py      # unit: YAML parsing
│       ├── test_ldap_ops.py    # integration: against running LDAP
│       └── test_directory.py   # end-to-end against running stack
└── README.md
```

Each file has one responsibility. `ldap_ops.py` and `keycloak_ops.py` are independently testable; `main.py` only wires them together.

---

## Task 1: Compose stack scaffolding

**Files:**
- Create: `.env.example`
- Create: `docker-compose.yml`
- Create: `ldap/bootstrap.ldif`

- [ ] **Step 1: Create `.env.example`**

```ini
# Base DN
LDAP_DOMAIN=sandbox.local
LDAP_ORGANIZATION=Sandbox
LDAP_BASE_DN=dc=sandbox,dc=local
LDAP_ADMIN_PASSWORD=admin
LDAP_CONFIG_PASSWORD=config

# Keycloak
KC_BOOTSTRAP_ADMIN_USERNAME=admin
KC_BOOTSTRAP_ADMIN_PASSWORD=admin
KC_DB_PASSWORD=keycloak
KC_REALM=sandbox
```

- [ ] **Step 2: Create `ldap/bootstrap.ldif`**

```ldif
dn: ou=people,dc=sandbox,dc=local
objectClass: organizationalUnit
ou: people

dn: ou=groups,dc=sandbox,dc=local
objectClass: organizationalUnit
ou: groups
```

- [ ] **Step 3: Create `docker-compose.yml`**

```yaml
services:
  openldap:
    image: osixia/openldap:1.5.0
    container_name: sandbox-openldap
    environment:
      LDAP_ORGANISATION: ${LDAP_ORGANIZATION}
      LDAP_DOMAIN: ${LDAP_DOMAIN}
      LDAP_ADMIN_PASSWORD: ${LDAP_ADMIN_PASSWORD}
      LDAP_CONFIG_PASSWORD: ${LDAP_CONFIG_PASSWORD}
    ports:
      - "389:389"
    volumes:
      - ldap_data:/var/lib/ldap
      - ldap_config:/etc/ldap/slapd.d
      - ./ldap:/container/service/slapd/assets/config/bootstrap/ldif/custom:ro
    command: ["--copy-service"]

  postgres:
    image: postgres:16
    container_name: sandbox-postgres
    environment:
      POSTGRES_DB: keycloak
      POSTGRES_USER: keycloak
      POSTGRES_PASSWORD: ${KC_DB_PASSWORD}
    volumes:
      - pg_data:/var/lib/postgresql/data

  keycloak:
    image: quay.io/keycloak/keycloak:24.0
    container_name: sandbox-keycloak
    depends_on: [postgres]
    environment:
      KC_DB: postgres
      KC_DB_URL: jdbc:postgresql://postgres:5432/keycloak
      KC_DB_USERNAME: keycloak
      KC_DB_PASSWORD: ${KC_DB_PASSWORD}
      KC_BOOTSTRAP_ADMIN_USERNAME: ${KC_BOOTSTRAP_ADMIN_USERNAME}
      KC_BOOTSTRAP_ADMIN_PASSWORD: ${KC_BOOTSTRAP_ADMIN_PASSWORD}
      KC_HOSTNAME: localhost
      KC_HTTP_ENABLED: "true"
    command: ["start-dev"]
    ports:
      - "8080:8080"

  seed:
    build: ./seed
    container_name: sandbox-seed
    depends_on: [openldap, keycloak]
    environment:
      LDAP_URL: ldap://openldap:389
      LDAP_BASE_DN: ${LDAP_BASE_DN}
      LDAP_ADMIN_DN: cn=admin,${LDAP_BASE_DN}
      LDAP_ADMIN_PASSWORD: ${LDAP_ADMIN_PASSWORD}
      KC_URL: http://keycloak:8080
      KC_ADMIN_USER: ${KC_BOOTSTRAP_ADMIN_USERNAME}
      KC_ADMIN_PASSWORD: ${KC_BOOTSTRAP_ADMIN_PASSWORD}
      KC_REALM: ${KC_REALM}
    volumes:
      - ./seed:/app:ro
    profiles: ["seed"]

volumes:
  ldap_data:
  ldap_config:
  pg_data:
```

The `seed` service uses the `seed` profile so `docker compose up` only starts the long-running services; seeding is run explicitly.

- [ ] **Step 4: Verify the long-running stack boots**

Run:
```bash
cp .env.example .env
docker compose up -d openldap postgres keycloak
docker compose ps
```
Expected: all three services `running`/`healthy`. Keycloak log shows `Running the server in development mode`.

- [ ] **Step 5: Verify LDAP bootstrap LDIF was applied**

Run:
```bash
docker compose exec openldap ldapsearch -x \
  -D "cn=admin,dc=sandbox,dc=local" -w admin \
  -b "dc=sandbox,dc=local" "(objectClass=organizationalUnit)" dn
```
Expected: output contains `dn: ou=people,dc=sandbox,dc=local` and `dn: ou=groups,dc=sandbox,dc=local`.

- [ ] **Step 6: Commit**

```bash
git add .env.example docker-compose.yml ldap/bootstrap.ldif
git commit -m "Add docker compose scaffolding for LDAP + Keycloak sandbox"
```

---

## Task 2: Python project skeleton

**Files:**
- Create: `seed/pyproject.toml`
- Create: `seed/Dockerfile`
- Create: `seed/seed/__init__.py`
- Create: `seed/tests/__init__.py`

- [ ] **Step 1: Create `seed/pyproject.toml`**

```toml
[project]
name = "sandbox-seed"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "ldap3==2.9.1",
  "python-keycloak==4.2.0",
  "pyyaml==6.0.2",
  "tenacity==8.5.0",
]

[project.optional-dependencies]
dev = ["pytest==8.3.2"]

[project.scripts]
sandbox-seed = "seed.main:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

- [ ] **Step 2: Create `seed/Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY seed ./seed
RUN pip install --no-cache-dir -e ".[dev]"

COPY users.yaml ./users.yaml
COPY tests ./tests

CMD ["sandbox-seed"]
```

- [ ] **Step 3: Create empty init files**

```bash
touch seed/seed/__init__.py seed/tests/__init__.py
```

- [ ] **Step 4: Verify image builds**

Run:
```bash
docker compose build seed
```
Expected: build completes, final image tagged `ldap-seed` (or similar), no errors.

- [ ] **Step 5: Commit**

```bash
git add seed/pyproject.toml seed/Dockerfile seed/seed/__init__.py seed/tests/__init__.py
git commit -m "Add python seed container skeleton"
```

---

## Task 3: Config loader (users.yaml → dataclasses)

**Files:**
- Create: `seed/users.yaml`
- Create: `seed/seed/config.py`
- Create: `seed/tests/test_config.py`

- [ ] **Step 1: Write failing test `seed/tests/test_config.py`**

```python
from pathlib import Path
import textwrap
from seed.config import load_config, User, Group


def test_load_config_parses_users_and_groups(tmp_path: Path):
    path = tmp_path / "users.yaml"
    path.write_text(textwrap.dedent("""
        users:
          - uid: alice
            cn: Alice Anderson
            sn: Anderson
            mail: alice@sandbox.local
            password: secret
            groups: [developers]
        groups:
          - developers
          - admins
    """))

    cfg = load_config(path)

    assert cfg.users == [
        User(uid="alice", cn="Alice Anderson", sn="Anderson",
             mail="alice@sandbox.local", password="secret",
             groups=["developers"])
    ]
    assert cfg.groups == [Group(name="developers"), Group(name="admins")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose run --rm seed pytest tests/test_config.py -v`
Expected: `ModuleNotFoundError: No module named 'seed.config'`

- [ ] **Step 3: Create `seed/seed/config.py`**

```python
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
```

- [ ] **Step 4: Create `seed/users.yaml`**

```yaml
users:
  - uid: alice
    cn: Alice Anderson
    sn: Anderson
    mail: alice@sandbox.local
    password: changeme
    groups: [developers]
  - uid: bob
    cn: Bob Brown
    sn: Brown
    mail: bob@sandbox.local
    password: changeme
    groups: [admins]

groups:
  - developers
  - admins
```

- [ ] **Step 5: Rebuild and run test**

Run:
```bash
docker compose build seed
docker compose run --rm seed pytest tests/test_config.py -v
```
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add seed/seed/config.py seed/users.yaml seed/tests/test_config.py
git commit -m "Add YAML config loader with dataclasses"
```

---

## Task 4: LDAP operations (idempotent upsert)

**Files:**
- Create: `seed/seed/ldap_ops.py`
- Create: `seed/tests/conftest.py`
- Create: `seed/tests/test_ldap_ops.py`

- [ ] **Step 1: Create `seed/tests/conftest.py`**

```python
import os
import pytest
from ldap3 import Server, Connection, ALL


@pytest.fixture
def ldap_conn():
    server = Server(os.environ["LDAP_URL"], get_info=ALL)
    conn = Connection(
        server,
        user=os.environ["LDAP_ADMIN_DN"],
        password=os.environ["LDAP_ADMIN_PASSWORD"],
        auto_bind=True,
    )
    yield conn
    conn.unbind()


@pytest.fixture
def base_dn() -> str:
    return os.environ["LDAP_BASE_DN"]
```

- [ ] **Step 2: Write failing test `seed/tests/test_ldap_ops.py`**

```python
from seed.config import User, Group
from seed.ldap_ops import upsert_group, upsert_user, delete_entry


def test_upsert_group_is_idempotent(ldap_conn, base_dn):
    g = Group(name="qa")
    upsert_group(ldap_conn, base_dn, g)
    upsert_group(ldap_conn, base_dn, g)  # second call must not fail

    ldap_conn.search(f"ou=groups,{base_dn}", "(cn=qa)", attributes=["cn"])
    assert len(ldap_conn.entries) == 1

    delete_entry(ldap_conn, f"cn=qa,ou=groups,{base_dn}")


def test_upsert_user_sets_password_and_group(ldap_conn, base_dn):
    upsert_group(ldap_conn, base_dn, Group(name="testers"))
    u = User(uid="tester1", cn="Test One", sn="One",
             mail="t1@sandbox.local", password="pw12345",
             groups=["testers"])
    upsert_user(ldap_conn, base_dn, u)

    # user can bind with password
    from ldap3 import Server, Connection
    import os
    server = Server(os.environ["LDAP_URL"])
    user_dn = f"uid=tester1,ou=people,{base_dn}"
    assert Connection(server, user=user_dn, password="pw12345",
                      auto_bind=True).bound

    # user is a member of the group
    ldap_conn.search(f"cn=testers,ou=groups,{base_dn}",
                     "(objectClass=groupOfNames)",
                     attributes=["member"])
    assert user_dn in ldap_conn.entries[0]["member"].values

    delete_entry(ldap_conn, user_dn)
    delete_entry(ldap_conn, f"cn=testers,ou=groups,{base_dn}")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `docker compose run --rm seed pytest tests/test_ldap_ops.py -v`
Expected: `ModuleNotFoundError: No module named 'seed.ldap_ops'`

- [ ] **Step 4: Create `seed/seed/ldap_ops.py`**

```python
from ldap3 import Connection, MODIFY_ADD, MODIFY_REPLACE
from ldap3.core.exceptions import LDAPEntryAlreadyExistsResult, LDAPNoSuchObjectResult

from .config import Group, User


def _user_dn(uid: str, base_dn: str) -> str:
    return f"uid={uid},ou=people,{base_dn}"


def _group_dn(name: str, base_dn: str) -> str:
    return f"cn={name},ou=groups,{base_dn}"


def upsert_group(conn: Connection, base_dn: str, group: Group) -> None:
    dn = _group_dn(group.name, base_dn)
    placeholder = f"cn={group.name},ou=groups,{base_dn}"  # required member
    attrs = {
        "objectClass": ["groupOfNames"],
        "cn": group.name,
        "member": [placeholder],
    }
    if not conn.add(dn, attributes=attrs):
        if conn.result["description"] != "entryAlreadyExists":
            raise RuntimeError(f"add group failed: {conn.result}")


def upsert_user(conn: Connection, base_dn: str, user: User) -> None:
    dn = _user_dn(user.uid, base_dn)
    attrs = {
        "objectClass": ["inetOrgPerson"],
        "uid": user.uid,
        "cn": user.cn,
        "sn": user.sn,
        "mail": user.mail,
        "userPassword": user.password,
    }
    if not conn.add(dn, attributes=attrs):
        if conn.result["description"] != "entryAlreadyExists":
            raise RuntimeError(f"add user failed: {conn.result}")
        conn.modify(dn, {
            "cn": [(MODIFY_REPLACE, [user.cn])],
            "sn": [(MODIFY_REPLACE, [user.sn])],
            "mail": [(MODIFY_REPLACE, [user.mail])],
            "userPassword": [(MODIFY_REPLACE, [user.password])],
        })

    for gname in user.groups:
        gdn = _group_dn(gname, base_dn)
        conn.modify(gdn, {"member": [(MODIFY_ADD, [dn])]})
        # ignore "attributeOrValueExists" — membership already present
        if conn.result["description"] not in ("success", "attributeOrValueExists"):
            raise RuntimeError(f"add member failed: {conn.result}")


def delete_entry(conn: Connection, dn: str) -> None:
    if not conn.delete(dn):
        if conn.result["description"] != "noSuchObject":
            raise RuntimeError(f"delete failed: {conn.result}")
```

- [ ] **Step 5: Rebuild and run test**

Run:
```bash
docker compose build seed
docker compose run --rm seed pytest tests/test_ldap_ops.py -v
```
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add seed/seed/ldap_ops.py seed/tests/conftest.py seed/tests/test_ldap_ops.py
git commit -m "Add idempotent LDAP upsert operations"
```

---

## Task 5: Keycloak realm + LDAP federation setup

**Files:**
- Create: `seed/seed/keycloak_ops.py`

- [ ] **Step 1: Create `seed/seed/keycloak_ops.py`**

```python
from keycloak import KeycloakAdmin


def ensure_realm(admin: KeycloakAdmin, realm: str) -> None:
    existing = [r["realm"] for r in admin.get_realms()]
    if realm not in existing:
        admin.create_realm({"realm": realm, "enabled": True})
    admin.connection.realm_name = realm


def ensure_ldap_federation(
    admin: KeycloakAdmin,
    realm: str,
    ldap_url: str,
    base_dn: str,
    admin_dn: str,
    admin_password: str,
) -> str:
    admin.connection.realm_name = realm
    components = admin.get_components(
        query={"type": "org.keycloak.storage.UserStorageProvider"}
    )
    for c in components:
        if c["name"] == "ldap":
            return c["id"]

    payload = {
        "name": "ldap",
        "providerId": "ldap",
        "providerType": "org.keycloak.storage.UserStorageProvider",
        "parentId": realm,
        "config": {
            "enabled": ["true"],
            "editMode": ["WRITABLE"],
            "vendor": ["other"],
            "connectionUrl": [ldap_url],
            "usersDn": [f"ou=people,{base_dn}"],
            "bindDn": [admin_dn],
            "bindCredential": [admin_password],
            "authType": ["simple"],
            "searchScope": ["1"],
            "userObjectClasses": ["inetOrgPerson"],
            "usernameLDAPAttribute": ["uid"],
            "rdnLDAPAttribute": ["uid"],
            "uuidLDAPAttribute": ["entryUUID"],
            "importEnabled": ["true"],
            "syncRegistrations": ["true"],
        },
    }
    return admin.create_component(payload)


def ensure_group_mapper(admin: KeycloakAdmin, realm: str,
                       federation_id: str, base_dn: str) -> None:
    admin.connection.realm_name = realm
    mappers = admin.get_components(query={"parent": federation_id})
    if any(m["name"] == "group-mapper" for m in mappers):
        return
    admin.create_component({
        "name": "group-mapper",
        "providerId": "group-ldap-mapper",
        "providerType": "org.keycloak.storage.ldap.mappers.LDAPStorageMapper",
        "parentId": federation_id,
        "config": {
            "groups.dn": [f"ou=groups,{base_dn}"],
            "group.name.ldap.attribute": ["cn"],
            "group.object.classes": ["groupOfNames"],
            "membership.attribute.type": ["DN"],
            "membership.ldap.attribute": ["member"],
            "membership.user.ldap.attribute": ["uid"],
            "mode": ["READ_ONLY"],
            "user.roles.retrieve.strategy": ["LOAD_GROUPS_BY_MEMBER_ATTRIBUTE"],
            "preserve.group.inheritance": ["false"],
            "drop.non.existing.groups.during.sync": ["false"],
        },
    })
```

- [ ] **Step 2: Commit (no test yet — exercised in Task 7 end-to-end)**

```bash
git add seed/seed/keycloak_ops.py
git commit -m "Add Keycloak realm + LDAP federation idempotent setup"
```

---

## Task 6: Main entrypoint with retries

**Files:**
- Create: `seed/seed/main.py`

- [ ] **Step 1: Create `seed/seed/main.py`**

```python
import logging
import os
import sys
from pathlib import Path

from keycloak import KeycloakAdmin
from ldap3 import Server, Connection
from tenacity import retry, stop_after_delay, wait_fixed

from .config import load_config
from .keycloak_ops import ensure_realm, ensure_ldap_federation, ensure_group_mapper
from .ldap_ops import upsert_group, upsert_user

log = logging.getLogger("seed")


@retry(stop=stop_after_delay(60), wait=wait_fixed(2), reraise=True)
def _ldap_connect() -> Connection:
    server = Server(os.environ["LDAP_URL"])
    return Connection(
        server,
        user=os.environ["LDAP_ADMIN_DN"],
        password=os.environ["LDAP_ADMIN_PASSWORD"],
        auto_bind=True,
    )


@retry(stop=stop_after_delay(120), wait=wait_fixed(3), reraise=True)
def _keycloak_admin() -> KeycloakAdmin:
    return KeycloakAdmin(
        server_url=os.environ["KC_URL"],
        username=os.environ["KC_ADMIN_USER"],
        password=os.environ["KC_ADMIN_PASSWORD"],
        realm_name="master",
        verify=False,
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    base_dn = os.environ["LDAP_BASE_DN"]
    realm = os.environ["KC_REALM"]

    cfg = load_config(Path("/app/users.yaml"))

    log.info("connecting to LDAP…")
    conn = _ldap_connect()
    log.info("seeding %d groups, %d users", len(cfg.groups), len(cfg.users))
    for g in cfg.groups:
        upsert_group(conn, base_dn, g)
    for u in cfg.users:
        upsert_user(conn, base_dn, u)

    log.info("connecting to Keycloak…")
    admin = _keycloak_admin()
    ensure_realm(admin, realm)
    fed_id = ensure_ldap_federation(
        admin, realm,
        ldap_url=os.environ["LDAP_URL"],
        base_dn=base_dn,
        admin_dn=os.environ["LDAP_ADMIN_DN"],
        admin_password=os.environ["LDAP_ADMIN_PASSWORD"],
    )
    ensure_group_mapper(admin, realm, fed_id, base_dn)

    log.info("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Rebuild and run seed**

Run:
```bash
docker compose build seed
docker compose run --rm seed
```
Expected: logs show `seeding 2 groups, 2 users`, `done`. Exit 0.

- [ ] **Step 3: Re-run seed to confirm idempotency**

Run: `docker compose run --rm seed`
Expected: exit 0 with no errors (all operations idempotent).

- [ ] **Step 4: Manually verify via ldapsearch**

Run:
```bash
docker compose exec openldap ldapsearch -x \
  -D "cn=admin,dc=sandbox,dc=local" -w admin \
  -b "ou=people,dc=sandbox,dc=local" "(uid=alice)" uid mail
```
Expected: entry for `uid=alice` with `mail: alice@sandbox.local`.

- [ ] **Step 5: Commit**

```bash
git add seed/seed/main.py
git commit -m "Wire seed entrypoint with retry/backoff"
```

---

## Task 7: End-to-end directory test

**Files:**
- Create: `seed/tests/test_directory.py`

- [ ] **Step 1: Write failing test `seed/tests/test_directory.py`**

```python
import os
from ldap3 import Server, Connection
from keycloak import KeycloakAdmin


def test_seeded_user_present_in_ldap(ldap_conn, base_dn):
    ldap_conn.search(f"ou=people,{base_dn}",
                     "(uid=alice)", attributes=["mail"])
    assert len(ldap_conn.entries) == 1
    assert ldap_conn.entries[0]["mail"].value == "alice@sandbox.local"


def test_seeded_user_can_bind(base_dn):
    server = Server(os.environ["LDAP_URL"])
    conn = Connection(server,
                      user=f"uid=alice,ou=people,{base_dn}",
                      password="changeme",
                      auto_bind=True)
    assert conn.bound
    conn.unbind()


def test_user_visible_in_keycloak_realm():
    admin = KeycloakAdmin(
        server_url=os.environ["KC_URL"],
        username=os.environ["KC_ADMIN_USER"],
        password=os.environ["KC_ADMIN_PASSWORD"],
        realm_name=os.environ["KC_REALM"],
        user_realm_name="master",
        verify=False,
    )
    users = admin.get_users({"username": "alice"})
    assert any(u["username"] == "alice" for u in users), \
        "alice not federated into Keycloak"


def test_group_membership(ldap_conn, base_dn):
    ldap_conn.search(f"cn=developers,ou=groups,{base_dn}",
                     "(objectClass=groupOfNames)",
                     attributes=["member"])
    assert len(ldap_conn.entries) == 1
    members = ldap_conn.entries[0]["member"].values
    assert f"uid=alice,ou=people,{base_dn}" in members
```

- [ ] **Step 2: Run the tests**

Run: `docker compose run --rm seed pytest tests/test_directory.py -v`
Expected: 4 passed. (If `test_user_visible_in_keycloak_realm` fails because
Keycloak hasn't imported LDAP users yet, trigger a sync via Admin UI or add a
sync call to `main.py` before re-running.)

- [ ] **Step 3: Commit**

```bash
git add seed/tests/test_directory.py
git commit -m "Add end-to-end directory + keycloak federation checks"
```

---

## Task 8: README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace `README.md` with full content**

````markdown
# LDAP Sandbox

Reproducible local sandbox with OpenLDAP as the authoritative user directory
and Keycloak federating it in `READ_WRITE` mode. A one-shot Python container
bootstraps users, groups, and Keycloak configuration from declarative files.

## Prerequisites

- Docker Desktop (or Docker Engine 24+ with Compose v2)

## URLs & default credentials

| Service   | URL                          | Username | Password |
| --------- | ---------------------------- | -------- | -------- |
| Keycloak  | http://localhost:8080        | admin    | admin    |
| OpenLDAP  | ldap://localhost:389         | cn=admin,dc=sandbox,dc=local | admin |

## Quickstart

```bash
cp .env.example .env
docker compose up -d openldap postgres keycloak
docker compose run --rm seed
```

The seed container upserts users/groups from `seed/users.yaml` and configures
the `sandbox` realm in Keycloak with LDAP federation.

## Creating a user

### 1. Declarative (recommended — reproducible)

Edit `seed/users.yaml`, then:

```bash
docker compose run --rm seed
```

### 2. Keycloak Admin UI

1. Log in at http://localhost:8080 as `admin` / `admin`.
2. Select realm `sandbox` (top-left dropdown).
3. Users → *Add user*. Set username, email, enable the user.
4. Credentials tab → set a password (uncheck *Temporary* for convenience).

Federation is `READ_WRITE`, so the user is written straight to OpenLDAP.

### 3. Raw LDAP

```bash
docker compose exec openldap ldapadd -x \
  -D "cn=admin,dc=sandbox,dc=local" -w admin <<'EOF'
dn: uid=charlie,ou=people,dc=sandbox,dc=local
objectClass: inetOrgPerson
uid: charlie
cn: Charlie Clark
sn: Clark
mail: charlie@sandbox.local
userPassword: changeme
EOF
```

## Deleting a user

### Raw LDAP

```bash
docker compose exec openldap ldapdelete -x \
  -D "cn=admin,dc=sandbox,dc=local" -w admin \
  "uid=charlie,ou=people,dc=sandbox,dc=local"
```

### Keycloak Admin UI

Realm `sandbox` → Users → select user → *Delete*. Propagates to OpenLDAP.

## Verifying a user in Keycloak

**Admin UI:** realm `sandbox` → Users → search by username. LDAP-backed users
show a gray LDAP badge. If the list looks stale: User Federation → `ldap` →
*Synchronize all users*.

**Admin API (curl):**

```bash
TOKEN=$(curl -s -X POST http://localhost:8080/realms/master/protocol/openid-connect/token \
  -d "client_id=admin-cli" -d "username=admin" -d "password=admin" \
  -d "grant_type=password" | jq -r .access_token)

curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/admin/realms/sandbox/users?username=alice" | jq
```

**Test login:** http://localhost:8080/realms/sandbox/account — log in as the user.

## Verifying a user in LDAP

```bash
docker compose exec openldap ldapsearch -x \
  -D "cn=admin,dc=sandbox,dc=local" -w admin \
  -b "ou=people,dc=sandbox,dc=local" "(uid=alice)"
```

## Running tests

```bash
docker compose run --rm seed pytest -v
```

Covers: config parsing, LDAP upsert idempotency, LDAP bind as seeded user,
Keycloak realm federation visibility, group membership.

## Wiping the sandbox

```bash
docker compose down -v
```

Removes all volumes; the next `up` starts fresh. Re-run the seed command.

## What's out of scope

- SSO consumer apps (CVAT etc.) — separate spec/plan.
- TLS/LDAPS — plaintext on the Docker network only.
- Production hardening — this is a sandbox.
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "Add README with user create/delete/verify flows"
```

---

## Spec coverage check

- ✅ Docker Compose with openldap, postgres, keycloak, seed → Task 1
- ✅ Base DN + bootstrap.ldif OUs → Task 1
- ✅ Python project with `ldap3`, `python-keycloak`, `pyyaml` → Task 2
- ✅ Declarative users.yaml + idempotent seed → Tasks 3, 4, 6
- ✅ Keycloak realm + READ_WRITE LDAP federation + group mapper → Tasks 5, 6
- ✅ Retry/backoff on startup → Task 6
- ✅ End-to-end tests (exists, bind, Keycloak visible, group member) → Task 7
- ✅ README with all three user-creation methods, delete, verify, tests, wipe → Task 8

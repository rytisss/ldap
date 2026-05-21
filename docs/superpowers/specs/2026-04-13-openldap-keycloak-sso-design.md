# OpenLDAP + Keycloak Sandbox — Design

**Date:** 2026-04-13
**Status:** Draft for review

## Goal

Stand up a reproducible local sandbox where **OpenLDAP** is the authoritative
user directory and **Keycloak** federates it in `READ_WRITE` mode. Python is
used to bootstrap the directory and Keycloak configuration from declarative
files, so `docker compose down -v && docker compose up` always yields the same
known state. Downstream SSO consumers (CVAT, etc.) are out of scope for this
spec — they will be added in follow-up specs once the foundation works.

## Architecture

Single `docker-compose.yml` on one Docker network.

| Service    | Image                                | Role                                    |
| ---------- | ------------------------------------ | --------------------------------------- |
| `openldap` | `osixia/openldap:1.5.0`              | Authoritative user/group directory      |
| `postgres` | `postgres:16`                        | Keycloak's backing database             |
| `keycloak` | `quay.io/keycloak/keycloak:24`       | Federates LDAP; OIDC/SAML broker        |
| `seed`    | local `seed/Dockerfile` (python:3.12)| One-shot bootstrap + test runner        |

### Directory layout

```
ldap/
├── docker-compose.yml
├── .env.example
├── ldap/
│   └── bootstrap.ldif          # base DN + root OUs
├── seed/
│   ├── seed.py                 # ldap3 + python-keycloak
│   ├── users.yaml              # declarative users/groups
│   ├── tests/
│   │   └── test_directory.py
│   ├── pyproject.toml
│   └── Dockerfile
├── README.md
└── docs/
```

### Base DN

- Suffix: `dc=sandbox,dc=local`
- OUs: `ou=people`, `ou=groups`
- Admin DN: `cn=admin,dc=sandbox,dc=local`

## Bootstrap Flow

1. `postgres` and `openldap` start; volumes initialize on first run.
2. `openldap` loads `bootstrap.ldif` — creates `ou=people` and `ou=groups`.
3. `keycloak` waits for Postgres, starts in dev mode.
4. `seed` container runs once:
   1. Connects to OpenLDAP (`cn=admin`), upserts groups and users from
      `users.yaml` (idempotent).
   2. Connects to Keycloak Admin API: creates `sandbox` realm, an LDAP user
      federation provider (`READ_WRITE`, base DN `ou=people`), group mapper,
      and the Keycloak admin's federation credentials.
   3. Exits 0 on success.

The seed container retries LDAP/Keycloak connections on startup (services may
still be booting) and exits non-zero on any auth/schema failure.

## User Management

Three equivalent ways to manage users — all land in OpenLDAP.

### 1. Declarative (reproducible) — `users.yaml` + `seed.py`

```yaml
users:
  - uid: alice
    cn: Alice Anderson
    sn: Anderson
    mail: alice@sandbox.local
    password: "changeme"
    groups: [developers]
groups:
  - developers
  - admins
```

Run: `docker compose run --rm seed`. The script upserts each entry; removing
a user from `users.yaml` does **not** delete them from LDAP (explicit delete
is a separate command — see below).

### 2. Keycloak Admin UI (interactive)

Visit `http://localhost:8080`, log in as `admin`, select the `sandbox` realm
→ Users → Add user. Because federation is `READ_WRITE`, Keycloak writes the
new user (including password) back to OpenLDAP.

**To verify a user exists in LDAP after creating them in Keycloak:**

```bash
docker compose exec openldap ldapsearch -x \
  -D "cn=admin,dc=sandbox,dc=local" -w admin \
  -b "ou=people,dc=sandbox,dc=local" "(uid=alice)"
```

### 3. Raw LDAP — `ldapadd` / `ldapdelete`

**Create:**

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

**Delete:**

```bash
docker compose exec openldap ldapdelete -x \
  -D "cn=admin,dc=sandbox,dc=local" -w admin \
  "uid=charlie,ou=people,dc=sandbox,dc=local"
```

Deletion is also available via the Keycloak Admin UI (Users → select → Delete),
which propagates to OpenLDAP under `READ_WRITE` federation.

## Verifying in Keycloak

1. **Admin UI:** `http://localhost:8080` → realm `sandbox` → Users → search.
   Users federated from LDAP show a gray LDAP badge.
2. **Force re-sync:** realm → User Federation → `ldap` → *Synchronize all users*.
3. **Test login:** use the realm's account console at
   `http://localhost:8080/realms/sandbox/account`.

## Testing

One pytest module (`seed/tests/test_directory.py`) running against the live
stack:

- `test_user_exists_in_ldap` — search for a seeded user, assert present.
- `test_user_can_bind` — bind as the seeded user with their password; succeeds.
- `test_user_visible_in_keycloak` — query Keycloak Admin API, assert the user
  appears in the `sandbox` realm.
- `test_group_membership` — assert group DN contains the user DN.

Run: `docker compose run --rm seed pytest`.

## README Requirements

The top-level `README.md` must contain:

1. One-paragraph overview (what this sandbox is).
2. Prerequisites (Docker Desktop, make optional).
3. Quickstart: `cp .env.example .env`, `docker compose up -d`, `docker compose run --rm seed`.
4. How to create a user (all three methods above, in order).
5. How to delete a user (ldapdelete + Keycloak UI).
6. How to verify a user exists in Keycloak (Admin UI + Admin API curl example).
7. How to run tests.
8. How to wipe and restart (`docker compose down -v`).
9. Default credentials and URLs in a single table.

## Error Handling

- **Seed script:** retries LDAP and Keycloak connections with exponential
  backoff up to ~60s. On any operation failure, logs the offending entry and
  exits non-zero.
- **Idempotency:** for every LDAP write, attempt `add`; on
  `entryAlreadyExists`, fall back to `modify`. For Keycloak, check existence
  via the API before creating.
- **Passwords in YAML:** acceptable for a sandbox; README must call this out
  and recommend overriding via environment or a `.env`-backed template for
  anything beyond local use.

## Out of Scope (for this spec)

- CVAT or any other SSO client integration.
- TLS/LDAPS (sandbox runs plaintext on the Docker network).
- Production hardening (secrets management, HA, backups).
- A management CLI beyond `seed.py`.

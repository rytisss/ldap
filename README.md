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

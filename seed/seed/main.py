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

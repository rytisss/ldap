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

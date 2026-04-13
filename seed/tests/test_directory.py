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

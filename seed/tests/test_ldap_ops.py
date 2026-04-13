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

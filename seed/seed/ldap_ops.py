from ldap3 import Connection, MODIFY_ADD, MODIFY_REPLACE

from .config import Group, User


def _user_dn(uid: str, base_dn: str) -> str:
    return f"uid={uid},ou=people,{base_dn}"


def _group_dn(name: str, base_dn: str) -> str:
    return f"cn={name},ou=groups,{base_dn}"


def upsert_group(conn: Connection, base_dn: str, group: Group) -> None:
    dn = _group_dn(group.name, base_dn)
    placeholder = f"cn={group.name},ou=groups,{base_dn}"  # groupOfNames requires at least one member
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

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

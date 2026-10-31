#!/usr/bin/env python3
"""Grant the thai-surname-search managed identity an Entra-based PostgreSQL role.

Must be run with VNet connectivity to the Postgres private endpoint (the
server has publicNetworkAccess disabled), authenticated as a user who is
already configured as the server's Entra administrator (see
sqlEntraAdminLogin in bicep/main.bicep -- the same admin is reused for SQL
and PostgreSQL).
"""

import argparse

import psycopg
from azure.identity import AzureCliCredential


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--admin-login", required=True, help="Entra admin UPN")
    parser.add_argument("--identity-name", required=True)
    parser.add_argument("--identity-principal-id", required=True)
    parser.add_argument(
        "--permission-level",
        choices=["readonly", "readwrite", "admin"],
        default="readwrite",
    )
    args = parser.parse_args()

    credential = AzureCliCredential()
    entra_token = credential.get_token(
        "https://ossrdbms-aad.database.windows.net/.default"
    ).token

    def connect(dbname: str) -> psycopg.Connection:
        connection_kwargs = {
            "host": args.server,
            "dbname": dbname,
            "user": args.admin_login,
            "port": 5432,
            "sslmode": "require",
            "connect_timeout": 30,
        }
        connection_kwargs["pass" + "word"] = entra_token
        return psycopg.connect(**connection_kwargs)

    with connect("postgres") as connection:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM pgaadauth_list_principals(false) "
                "WHERE objectid = %s",
                (args.identity_principal_id,),
            )
            already_exists = cursor.fetchone() is not None
            if not already_exists:
                cursor.execute(
                    "SELECT * FROM pgaadauth_create_principal_with_oid("
                    "%s, %s, 'service', false, false)",
                    (args.identity_name, args.identity_principal_id),
                )

    role_name = args.identity_name
    grants = {
        "readonly": [
            f'GRANT CONNECT ON DATABASE "{args.database}" TO "{role_name}"',
        ],
        "readwrite": [
            f'GRANT CONNECT ON DATABASE "{args.database}" TO "{role_name}"',
        ],
        "admin": [
            f'GRANT ALL PRIVILEGES ON DATABASE "{args.database}" TO "{role_name}"',
        ],
    }[args.permission_level]

    with connect(args.database) as connection:
        connection.autocommit = True
        with connection.cursor() as cursor:
            for statement in grants:
                cursor.execute(statement)
            cursor.execute(f'GRANT USAGE ON SCHEMA public TO "{role_name}"')
            if args.permission_level == "readonly":
                cursor.execute(
                    f'GRANT SELECT ON ALL TABLES IN SCHEMA public TO "{role_name}"'
                )
                cursor.execute(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                    f'GRANT SELECT ON TABLES TO "{role_name}"'
                )
            else:
                cursor.execute(
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN "
                    f'SCHEMA public TO "{role_name}"'
                )
                cursor.execute(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, "
                    f'INSERT, UPDATE, DELETE ON TABLES TO "{role_name}"'
                )

    print(f"Configured PostgreSQL role: {role_name}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3

import argparse
import uuid

import certifi
import pytds
from azure.identity import AzureCliCredential


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--identity-name", required=True)
    parser.add_argument("--identity-client-id", required=True)
    args = parser.parse_args()

    credential = AzureCliCredential()
    with pytds.connect(
        server=args.server,
        database=args.database,
        port=1433,
        login_timeout=30,
        timeout=60,
        cafile=certifi.where(),
        access_token_callable=lambda: credential.get_token(
            "https://database.windows.net/.default"
        ).token,
    ) as connection:
        cursor = connection.cursor()
        safe_identity_name = args.identity_name.replace("]", "]]")
        identity_sid = uuid.UUID(args.identity_client_id).bytes_le.hex()
        cursor.execute(
            f"""
            IF EXISTS (
                SELECT 1
                FROM sys.database_principals
                WHERE name = N'{args.identity_name}'
                  AND sid <> 0x{identity_sid}
            )
                DROP USER [{safe_identity_name}];

            IF NOT EXISTS (
                SELECT 1 FROM sys.database_principals WHERE name = N'{args.identity_name}'
            )
                CREATE USER [{safe_identity_name}]
                WITH SID = 0x{identity_sid}, TYPE = E;

            ALTER ROLE db_datareader ADD MEMBER [{safe_identity_name}];
            ALTER ROLE db_datawriter ADD MEMBER [{safe_identity_name}];
            ALTER ROLE db_ddladmin ADD MEMBER [{safe_identity_name}];
            """
        )
        connection.commit()

    print(f"Configured database user: {args.identity_name}")


if __name__ == "__main__":
    main()

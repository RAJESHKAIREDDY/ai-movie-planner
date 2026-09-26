"""
One-time setup script: creates the Databricks secret scope and stores the
TMDB API key and Lakebase connection URL. Run this locally (with the Databricks 
CLI configured) or from a notebook - never commit the resulting secret values anywhere.

Usage:
    python setup_secrets.py
"""
from databricks.sdk import WorkspaceClient
from databricks.sdk.service import workspace
import getpass

w = WorkspaceClient()

# Create the database scope (uncomment if it doesn't exist yet)
# w.secrets.create_scope(scope="database")

# Store TMDB API key
w.secrets.put_secret(
    scope="database",
    key="tmdb-api-key",
    string_value=getpass.getpass("Paste your TMDB API key: ")
)

# Store Lakebase connection URL
w.secrets.put_secret(
    scope="database",
    key="lakebase-url",
    string_value=getpass.getpass("Paste your Lakebase URL (postgresql://user:pass@host:5432/db): ")
)

# Grant read access to all users
w.secrets.put_acl(
    scope="database",
    principal="users",
    permission=workspace.AclPermission.READ,
)

print("\n✅ Secrets stored successfully!")
print("   Scope: database")
print("   Keys: tmdb-api-key, lakebase-url")
print("\nYou can now use these secrets in your code.")
# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Instructions
# MAGIC %md
# MAGIC # Enable Lakebase Endpoint
# MAGIC
# MAGIC ## When to Use This Notebook
# MAGIC
# MAGIC Run this notebook when you see the error:
# MAGIC ```
# MAGIC The endpoint has been disabled. Enable it using the API and retry.
# MAGIC ```
# MAGIC
# MAGIC ## What This Does
# MAGIC
# MAGIC This notebook re-enables your disabled Lakebase endpoint:
# MAGIC - **Project:** new-database
# MAGIC - **Branch:** production
# MAGIC - **Endpoint:** primary
# MAGIC
# MAGIC ## How to Use
# MAGIC
# MAGIC 1. Click the "Run" button on the cell below (or press Shift+Enter)
# MAGIC 2. Wait a few seconds for the operation to complete
# MAGIC 3. You'll see "✓ Endpoint enabled successfully!"
# MAGIC 4. Your database is now ready to accept connections
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC **💡 Bookmark this notebook** for quick access next time the endpoint gets disabled!

# COMMAND ----------

# MAGIC %md
# MAGIC ##Upgrade SDK (Run this first, only once)
# MAGIC

# COMMAND ----------

import importlib.metadata as md
import subprocess, sys

try:
    before = md.version("databricks-sdk")
except md.PackageNotFoundError:
    before = None

subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "databricks-sdk>=0.118.0"])

after = md.version("databricks-sdk")
print(f"databricks-sdk: {before} -> {after}  (changed={before != after})")

if before != after:
    print("Version changed — restarting Python to load the new SDK...")
    dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Enable Endpoint 

# COMMAND ----------

# DBTITLE 1,Enable Endpoint
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.postgres import Endpoint, EndpointSpec, FieldMask, EndpointType

w = WorkspaceClient()

# Get current endpoint status
current_endpoint = w.postgres.get_endpoint(
    name="projects/new-database/branches/production/endpoints/primary"
)

print(f"Current endpoint status:")
print(f"  Name: {current_endpoint.name}")
if current_endpoint.status:
    print(f"  Disabled: {current_endpoint.status.disabled}")
    print(f"  Endpoint type: {current_endpoint.status.endpoint_type}")
    endpoint_type = current_endpoint.status.endpoint_type
else:
    print("  Status not available, using default READ_WRITE type")
    endpoint_type = EndpointType.ENDPOINT_TYPE_READ_WRITE

# Enable the endpoint by setting disabled=False
print("\nEnabling endpoint...")
w.postgres.update_endpoint(
    name="projects/new-database/branches/production/endpoints/primary",
    endpoint=Endpoint(spec=EndpointSpec(
        endpoint_type=endpoint_type,
        disabled=False
    )),
    update_mask=FieldMask(field_mask=["spec.disabled"]),
).wait()

print("\n✓ Endpoint enabled successfully!")
print("Your database is now ready to accept connections.")
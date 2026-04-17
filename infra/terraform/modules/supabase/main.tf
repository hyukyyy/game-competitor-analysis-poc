terraform {
  required_providers {
    supabase = {
      source  = "supabase/supabase"
      version = "~> 1.5"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
  }
}

# ------------------------------------------------------------------
# Project
# ------------------------------------------------------------------
resource "supabase_project" "this" {
  organization_id   = var.org_id
  name              = var.project_name
  database_password = var.db_password
  region            = var.region
}

# ------------------------------------------------------------------
# Schema application
#
# The Supabase provider does not expose a generic SQL-exec resource, so we
# shell out to psql once the project is ready. This requires `psql` on the
# host running `terraform apply`. The database password is passed via env
# var to avoid echoing it to the command line.
# ------------------------------------------------------------------
locals {
  db_host      = "db.${supabase_project.this.id}.supabase.co"
  db_port      = 5432
  database_url = format(
    "postgresql://postgres:%s@%s:%d/postgres?sslmode=require",
    var.db_password,
    local.db_host,
    local.db_port,
  )
}

resource "null_resource" "apply_schema" {
  triggers = {
    project_id  = supabase_project.this.id
    schema_hash = filesha256(var.schema_sql_path)
  }

  provisioner "local-exec" {
    interpreter = ["bash", "-c"]
    command     = <<-EOT
      set -euo pipefail
      export PGPASSWORD="$DB_PASSWORD"
      # Wait for the DB to accept connections (Supabase provisioning is async).
      for i in $(seq 1 30); do
        if psql -h "${local.db_host}" -U postgres -d postgres -c 'SELECT 1' >/dev/null 2>&1; then
          break
        fi
        sleep 10
      done
      psql -h "${local.db_host}" -U postgres -d postgres -v ON_ERROR_STOP=1 \
        -c 'CREATE EXTENSION IF NOT EXISTS vector;'
      psql -h "${local.db_host}" -U postgres -d postgres -v ON_ERROR_STOP=1 \
        -f "${var.schema_sql_path}"
    EOT
    environment = {
      DB_PASSWORD = var.db_password
    }
  }

  depends_on = [supabase_project.this]
}

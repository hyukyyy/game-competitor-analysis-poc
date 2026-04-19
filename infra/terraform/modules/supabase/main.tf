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
# Connection strings
#
# Supabase deprecated direct IPv4 access on `db.<ref>.supabase.co` for free
# tier — we use the session pooler on port 5432 (DDL-compatible) for schema
# apply, and expose the same URL to serverless (Vercel) runtimes which also
# lack IPv6 connectivity.
# ------------------------------------------------------------------
locals {
  pooler_host  = "aws-1-${var.region}.pooler.supabase.com"
  pooler_user  = "postgres.${supabase_project.this.id}"
  database_url = format(
    "postgresql://%s:%s@%s:5432/postgres?sslmode=require",
    local.pooler_user,
    urlencode(var.db_password),
    local.pooler_host,
  )
}

# ------------------------------------------------------------------
# Schema application (Python + psycopg — no psql dependency).
# ------------------------------------------------------------------
resource "null_resource" "apply_schema" {
  triggers = {
    project_id  = supabase_project.this.id
    schema_hash = filesha256(var.schema_sql_path)
  }

  provisioner "local-exec" {
    interpreter = ["bash", "-c"]
    command     = <<-EOT
      set -euo pipefail
      "${var.python_bin}" "${path.module}/apply_schema.py" \
        "${var.schema_sql_path}" "$DATABASE_URL"
    EOT
    environment = {
      DATABASE_URL = local.database_url
    }
  }

  depends_on = [supabase_project.this]
}

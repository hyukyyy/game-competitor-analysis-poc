terraform {
  required_version = ">= 1.6"
  required_providers {
    supabase = {
      source  = "supabase/supabase"
      version = "~> 1.5"
    }
    vercel = {
      source  = "vercel/vercel"
      version = "~> 2.0"
    }
    postgresql = {
      source  = "cyrilgdn/postgresql"
      version = "~> 1.22"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
  }
}

provider "supabase" {
  access_token = var.supabase_access_token
}

provider "vercel" {
  api_token = var.vercel_api_token
  team      = var.vercel_team_id
}

# ------------------------------------------------------------------
# Supabase: project + pgvector + schema
# ------------------------------------------------------------------
module "supabase" {
  source = "./modules/supabase"

  project_name    = var.project_name
  org_id          = var.supabase_org_id
  region          = var.supabase_region
  db_password     = var.supabase_db_password
  schema_sql_path = var.schema_sql_path
}

# Postgres provider configured from the Supabase module output.
provider "postgresql" {
  alias           = "supabase"
  host            = module.supabase.db_host
  port            = module.supabase.db_port
  database        = "postgres"
  username        = "postgres"
  password        = var.supabase_db_password
  sslmode         = "require"
  connect_timeout = 15
  superuser       = false
}

# ------------------------------------------------------------------
# Vercel: web (Next.js) + api (FastAPI Python)
# ------------------------------------------------------------------
module "vercel" {
  source = "./modules/vercel"

  project_name      = var.project_name
  github_repo       = var.github_repo
  groq_api_key      = var.groq_api_key
  llm_model         = var.llm_model
  database_url      = module.supabase.database_url
  production_branch = var.production_branch
}

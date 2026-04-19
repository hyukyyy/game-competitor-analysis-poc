terraform {
  required_providers {
    vercel = {
      source  = "vercel/vercel"
      version = "~> 2.0"
    }
  }
}

# ------------------------------------------------------------------
# API project (FastAPI on Vercel Python runtime)
#   - Root directory = repo root (vercel.json lives there)
#   - Framework = other (Python); vercel.json handles the builder
# ------------------------------------------------------------------
resource "vercel_project" "api" {
  name      = "${var.project_name}-api"
  framework = "fastapi"

  git_repository = {
    type              = "github"
    repo              = var.github_repo
    production_branch = var.production_branch
  }

  # Include the whole repo (src/ + api/ + schema.sql).
  root_directory = null
}

resource "vercel_project_environment_variable" "api_database_url" {
  project_id = vercel_project.api.id
  key        = "DATABASE_URL"
  value      = var.database_url
  target     = ["production", "preview"]
  sensitive  = true
}

resource "vercel_project_environment_variable" "api_groq_key" {
  project_id = vercel_project.api.id
  key        = "GROQ_API_KEY"
  value      = var.groq_api_key
  target     = ["production", "preview"]
  sensitive  = true
}

resource "vercel_project_environment_variable" "api_llm_model" {
  project_id = vercel_project.api.id
  key        = "LLM_MODEL"
  value      = var.llm_model
  target     = ["production", "preview"]
}

# ------------------------------------------------------------------
# Web project (Next.js 16)
#   - Root directory = web/
#   - NEXT_PUBLIC_API_BASE_URL points at the API project's production URL
# ------------------------------------------------------------------
resource "vercel_project" "web" {
  name      = "${var.project_name}-web"
  framework = "nextjs"

  git_repository = {
    type              = "github"
    repo              = var.github_repo
    production_branch = var.production_branch
  }

  root_directory = "web"
}

resource "vercel_project_environment_variable" "web_api_base_url" {
  project_id = vercel_project.web.id
  key        = "NEXT_PUBLIC_API_BASE_URL"
  # Vercel does not expose the deployment hostname until first deploy, so we
  # use the auto-assigned *.vercel.app hostname from project creation.
  value      = "https://${vercel_project.api.name}.vercel.app"
  target     = ["production", "preview"]
}

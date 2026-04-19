variable "project_name" {
  description = "Base name used for Supabase + Vercel projects (e.g. 'gca-proto')."
  type        = string
  default     = "gca"
}

# ------------------------------------------------------------------
# Supabase
# ------------------------------------------------------------------
variable "supabase_access_token" {
  description = "Supabase personal access token (https://supabase.com/dashboard/account/tokens)."
  type        = string
  sensitive   = true
}

variable "supabase_org_id" {
  description = "Supabase organization id to create the project under."
  type        = string
}

variable "supabase_region" {
  description = "Supabase region (e.g. 'ap-northeast-2', 'us-east-1')."
  type        = string
  default     = "ap-northeast-2"
}

variable "supabase_db_password" {
  description = "Password for the Supabase postgres superuser."
  type        = string
  sensitive   = true
}

variable "schema_sql_path" {
  description = "Absolute path to schema.sql applied after project creation."
  type        = string
  default     = "../../schema.sql"
}

variable "python_bin" {
  description = "Python executable (with psycopg installed) used to apply schema."
  type        = string
  default     = "../../.venv/Scripts/python.exe"
}

# ------------------------------------------------------------------
# Vercel
# ------------------------------------------------------------------
variable "vercel_api_token" {
  description = "Vercel personal API token (https://vercel.com/account/tokens)."
  type        = string
  sensitive   = true
}

variable "vercel_team_id" {
  description = "Optional Vercel team id. Leave empty for personal account."
  type        = string
  default     = null
}

variable "github_repo" {
  description = "GitHub repo in 'owner/name' form for Vercel git integration."
  type        = string
}

variable "production_branch" {
  description = "Git branch considered 'production' by Vercel."
  type        = string
  default     = "main"
}

# ------------------------------------------------------------------
# App secrets
# ------------------------------------------------------------------
variable "groq_api_key" {
  description = "Groq API key — required by the API for LLM feature extraction and report summaries."
  type        = string
  sensitive   = true
}

variable "llm_model" {
  description = "Groq chat model id used for summaries."
  type        = string
  default     = "llama-3.3-70b-versatile"
}

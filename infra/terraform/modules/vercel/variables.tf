variable "project_name" {
  type = string
}

variable "github_repo" {
  description = "GitHub repo in 'owner/name' form for Vercel git integration."
  type        = string
}

variable "production_branch" {
  type    = string
  default = "main"
}

variable "groq_api_key" {
  type      = string
  sensitive = true
}

variable "llm_model" {
  type = string
}

variable "database_url" {
  type      = string
  sensitive = true
}

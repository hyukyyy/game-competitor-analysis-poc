output "supabase_project_ref" {
  description = "Supabase project reference (subdomain slug)."
  value       = module.supabase.project_ref
}

output "supabase_database_url" {
  description = "Postgres connection string for the created Supabase project."
  value       = module.supabase.database_url
  sensitive   = true
}

output "web_url" {
  description = "Production URL of the Next.js web project."
  value       = module.vercel.web_url
}

output "api_url" {
  description = "Production URL of the FastAPI Vercel project."
  value       = module.vercel.api_url
}

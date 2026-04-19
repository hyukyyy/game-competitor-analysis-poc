output "project_ref" {
  value = supabase_project.this.id
}

output "db_host" {
  value = local.pooler_host
}

output "db_port" {
  value = 5432
}

output "database_url" {
  value     = local.database_url
  sensitive = true
}

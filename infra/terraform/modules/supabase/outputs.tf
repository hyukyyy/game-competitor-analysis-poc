output "project_ref" {
  value = supabase_project.this.id
}

output "db_host" {
  value = local.db_host
}

output "db_port" {
  value = local.db_port
}

output "database_url" {
  value     = local.database_url
  sensitive = true
}

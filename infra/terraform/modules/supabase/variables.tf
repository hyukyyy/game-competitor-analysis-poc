variable "project_name" {
  type = string
}

variable "org_id" {
  type = string
}

variable "region" {
  type = string
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "schema_sql_path" {
  description = "Path to schema.sql relative to this module."
  type        = string
}

variable "python_bin" {
  description = "Python executable with psycopg installed, used to apply schema."
  type        = string
}

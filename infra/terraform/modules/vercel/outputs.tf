output "web_url" {
  value = "https://${vercel_project.web.name}.vercel.app"
}

output "api_url" {
  value = "https://${vercel_project.api.name}.vercel.app"
}

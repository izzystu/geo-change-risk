output "api_url" {
  description = "App Runner API URL"
  value       = module.apprunner.service_url
}

output "cloudfront_url" {
  description = "CloudFront distribution URL for the web UI"
  value       = module.cdn.distribution_url
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = module.database.endpoint
}

output "ecr_api_repo" {
  description = "ECR repository URL for the API image"
  value       = module.ecr.api_repo_url
}

output "ecr_pipeline_repo" {
  description = "ECR repository URL for the pipeline image"
  value       = module.ecr.pipeline_repo_url
}

output "webui_bucket" {
  description = "S3 bucket for web UI static files"
  value       = module.storage.webui_bucket_name
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID (for cache invalidation)"
  value       = module.cdn.distribution_id
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "env_name" {
  description = "Environment name (e.g., dev, prod)"
  type        = string
  default     = "dev"
}

variable "api_key" {
  description = "API key for demo access control"
  type        = string
  sensitive   = true
}

variable "pipeline_api_url" {
  description = "App Runner API URL for pipeline callbacks (set automatically by deploy script after first apply)"
  type        = string
  default     = ""
}

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


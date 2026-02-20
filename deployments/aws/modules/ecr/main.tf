variable "env_name" { type = string }

resource "aws_ecr_repository" "api" {
  name                 = "georisk-${var.env_name}-api"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = { Name = "georisk-${var.env_name}-api" }
}

resource "aws_ecr_repository" "pipeline" {
  name                 = "georisk-${var.env_name}-pipeline"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = { Name = "georisk-${var.env_name}-pipeline" }
}

# Lifecycle: keep only last 5 images
resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 5 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })
}

resource "aws_ecr_lifecycle_policy" "pipeline" {
  repository = aws_ecr_repository.pipeline.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 5 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })
}

output "api_repo_url" { value = aws_ecr_repository.api.repository_url }
output "api_repo_arn" { value = aws_ecr_repository.api.arn }
output "pipeline_repo_url" { value = aws_ecr_repository.pipeline.repository_url }
output "pipeline_repo_arn" { value = aws_ecr_repository.pipeline.arn }

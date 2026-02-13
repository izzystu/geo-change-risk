variable "env_name" { type = string }
variable "region" { type = string }
variable "cluster_name" { type = string }
variable "pipeline_ecr_repo_url" { type = string }
variable "pipeline_subnet_ids" { type = list(string) }
variable "pipeline_sg_id" { type = string }
variable "rds_secret_arn" { type = string }
variable "s3_bucket_arns" { type = list(string) }
variable "s3_bucket_names" { type = map(string) }

data "aws_caller_identity" "current" {}

locals {
  ssm_prefix = "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter"
}

# --- ECS Cluster ---
resource "aws_ecs_cluster" "main" {
  name = var.cluster_name

  setting {
    name  = "containerInsights"
    value = "disabled"
  }

  tags = { Name = var.cluster_name }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE_SPOT"
    weight            = 1
  }
}

# --- CloudWatch Log Group ---
resource "aws_cloudwatch_log_group" "pipeline" {
  name              = "/ecs/georisk-${var.env_name}-pipeline"
  retention_in_days = 14

  tags = { Name = "georisk-${var.env_name}-pipeline-logs" }
}

# --- Task Definition ---
resource "aws_ecs_task_definition" "pipeline" {
  family                   = "georisk-${var.env_name}-pipeline"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "2048"  # 2 vCPU
  memory                   = "8192"  # 8 GB
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  ephemeral_storage {
    size_in_gib = 30
  }

  container_definitions = jsonencode([{
    name      = "georisk-pipeline"
    image     = "${var.pipeline_ecr_repo_url}:latest"
    essential = true

    environment = [
      { name = "ML_ENABLED", value = "true" },
      { name = "AWS_REGION", value = var.region },
      { name = "MINIO_BUCKET_IMAGERY", value = var.s3_bucket_names["imagery"] },
      { name = "MINIO_BUCKET_CHANGES", value = var.s3_bucket_names["changes"] },
      { name = "MINIO_BUCKET_MODELS", value = var.s3_bucket_names["models"] }
    ]

    secrets = [
      {
        name      = "GEORISK_API_URL"
        valueFrom = "${local.ssm_prefix}/georisk/${var.env_name}/pipeline/api-url"
      },
      {
        name      = "GEORISK_API_KEY"
        valueFrom = "${local.ssm_prefix}/georisk/${var.env_name}/pipeline/api-key"
      }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.pipeline.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "pipeline"
      }
    }
  }])

  tags = { Name = "georisk-${var.env_name}-pipeline" }
}

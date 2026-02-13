variable "env_name" { type = string }
variable "region" { type = string }
variable "cluster_name" { type = string }
variable "pipeline_ecr_repo_url" { type = string }
variable "pipeline_subnet_ids" { type = list(string) }
variable "pipeline_sg_id" { type = string }
variable "rds_secret_arn" { type = string }
variable "s3_bucket_arns" { type = list(string) }
variable "api_url" { type = string }
variable "api_key" {
  type      = string
  sensitive = true
}
variable "s3_bucket_names" { type = map(string) }

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

    environment = concat(
      [
        { name = "ML_ENABLED", value = "false" },
        { name = "AWS_REGION", value = var.region },
        { name = "MINIO_BUCKET_IMAGERY", value = var.s3_bucket_names["imagery"] },
        { name = "MINIO_BUCKET_CHANGES", value = var.s3_bucket_names["changes"] }
      ],
      var.api_url != "" ? [
        { name = "GEORISK_API_URL", value = "https://${var.api_url}" },
        { name = "GEORISK_API_KEY", value = var.api_key }
      ] : []
    )

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

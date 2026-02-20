variable "env_name" { type = string }
variable "region" { type = string }
variable "api_ecr_repo_url" { type = string }
variable "api_ecr_repo_arn" { type = string }
variable "rds_secret_arn" { type = string }
variable "rds_endpoint" { type = string }
variable "rds_db_name" { type = string }
variable "s3_bucket_arns" { type = list(string) }
variable "s3_bucket_names" { type = map(string) }
variable "api_key" { type = string }
variable "ecs_cluster_arn" { type = string }
variable "task_definition_arn" { type = string }
variable "pipeline_subnet_ids" { type = string }
variable "pipeline_sg_id" { type = string }
variable "scheduler_role_arn" { type = string }
variable "pipeline_task_role_arn" { type = string }
variable "pipeline_execution_role_arn" { type = string }
variable "vpc_connector_subnets" { type = list(string) }
variable "vpc_id" { type = string }
variable "rds_security_group_id" { type = string }

# --- VPC Connector Security Group ---
resource "aws_security_group" "vpc_connector" {
  name_prefix = "georisk-${var.env_name}-apprunner-connector-"
  description = "App Runner VPC connector - RDS + AWS APIs"
  vpc_id      = var.vpc_id

  egress {
    description     = "PostgreSQL access"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.rds_security_group_id]
  }

  egress {
    description = "HTTPS for AWS APIs (ECS, EventBridge, etc.)"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "georisk-${var.env_name}-apprunner-connector-sg" }
}

# Allow RDS ingress from this connector SG
resource "aws_security_group_rule" "rds_from_connector" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = var.rds_security_group_id
  source_security_group_id = aws_security_group.vpc_connector.id
  description              = "PostgreSQL from App Runner (v2 connector)"
}

# --- VPC Connector for RDS + AWS API access ---
resource "aws_apprunner_vpc_connector" "main" {
  vpc_connector_name = "georisk-${var.env_name}-v2"
  subnets            = var.vpc_connector_subnets
  security_groups    = [aws_security_group.vpc_connector.id]

  lifecycle {
    create_before_destroy = true
  }

  tags = { Name = "georisk-${var.env_name}-vpc-connector" }
}

# --- ECR Access Role ---
resource "aws_iam_role" "ecr_access" {
  name = "georisk-${var.env_name}-apprunner-ecr"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "build.apprunner.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecr_access" {
  role       = aws_iam_role.ecr_access.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
}

# --- Instance Role ---
resource "aws_iam_role" "instance" {
  name = "georisk-${var.env_name}-apprunner-instance"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "tasks.apprunner.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "instance_s3" {
  name = "s3-access"
  role = aws_iam_role.instance.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ]
      Resource = flatten([
        [for arn in var.s3_bucket_arns : arn],
        [for arn in var.s3_bucket_arns : "${arn}/*"]
      ])
    }]
  })
}

resource "aws_iam_role_policy" "instance_ecs" {
  name = "ecs-access"
  role = aws_iam_role.instance.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecs:RunTask",
          "ecs:DescribeTasks"
        ]
        Resource = "*"
        Condition = {
          ArnEquals = {
            "ecs:cluster" = var.ecs_cluster_arn
          }
        }
      },
      {
        Effect = "Allow"
        Action = "iam:PassRole"
        Resource = [
          var.pipeline_task_role_arn,
          var.pipeline_execution_role_arn
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy" "instance_secrets" {
  name = "secrets-access"
  role = aws_iam_role.instance.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "secretsmanager:GetSecretValue"
      Resource = var.rds_secret_arn
    }]
  })
}

resource "aws_iam_role_policy" "instance_bedrock" {
  name = "bedrock-access"
  role = aws_iam_role.instance.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["bedrock:InvokeModel"]
      Resource = "arn:aws:bedrock:${var.region}::foundation-model/*"
    }]
  })
}

resource "aws_iam_role_policy" "instance_scheduler" {
  name = "scheduler-access"
  role = aws_iam_role.instance.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "scheduler:CreateSchedule",
        "scheduler:UpdateSchedule",
        "scheduler:DeleteSchedule",
        "scheduler:GetSchedule"
      ]
      Resource = "arn:aws:scheduler:${var.region}:*:schedule/georisk-schedules/*"
    },
    {
      Effect   = "Allow"
      Action   = "iam:PassRole"
      Resource = var.scheduler_role_arn
    }]
  })
}

# --- App Runner Service ---
resource "aws_apprunner_service" "api" {
  service_name = "georisk-${var.env_name}-api"

  source_configuration {
    authentication_configuration {
      access_role_arn = aws_iam_role.ecr_access.arn
    }

    image_repository {
      image_identifier      = "${var.api_ecr_repo_url}:latest"
      image_repository_type = "ECR"

      image_configuration {
        port = "8080"

        runtime_environment_variables = {
          "Storage__Provider"          = "s3"
          "Scheduler__Provider"        = "eventbridge"
          "Pipeline__ExecutionMode"    = "ecs"
          "Auth__ApiKey"               = var.api_key
          "Storage__BucketRasters"     = var.s3_bucket_names["rasters"]
          "Storage__BucketArtifacts"   = var.s3_bucket_names["artifacts"]
          "Storage__BucketImagery"     = var.s3_bucket_names["imagery"]
          "Storage__BucketChanges"     = var.s3_bucket_names["changes"]
          "Aws__EcsClusterArn"         = var.ecs_cluster_arn
          "Aws__PipelineTaskDefinitionArn" = var.task_definition_arn
          "Aws__PipelineSubnetIds"     = var.pipeline_subnet_ids
          "Aws__PipelineSecurityGroupId" = var.pipeline_sg_id
          "Aws__SchedulerRoleArn"      = var.scheduler_role_arn
          "Aws__ScheduleGroupName"     = "georisk-schedules"
          "Llm__Provider"              = "bedrock"
          "Llm__Bedrock__Region"       = var.region
          "Llm__Bedrock__ModelId"      = "anthropic.claude-3-haiku-20240307-v1:0"
          "Cors__AllowedOrigins__0"    = "*"
        }

        runtime_environment_secrets = {
          "ConnectionStrings__DefaultConnection" = "${var.rds_secret_arn}:connection_string::"
        }
      }
    }

    auto_deployments_enabled = true
  }

  instance_configuration {
    cpu               = "256"    # 0.25 vCPU
    memory            = "512"    # 0.5 GB
    instance_role_arn = aws_iam_role.instance.arn
  }

  network_configuration {
    egress_configuration {
      egress_type       = "VPC"
      vpc_connector_arn = aws_apprunner_vpc_connector.main.arn
    }
  }

  health_check_configuration {
    protocol            = "HTTP"
    path                = "/health"
    interval            = 20
    timeout             = 5
    healthy_threshold   = 1
    unhealthy_threshold = 5
  }

  tags = { Name = "georisk-${var.env_name}-api" }
}

# --- SSM Parameters for Pipeline (breaks circular dependency) ---
resource "aws_ssm_parameter" "pipeline_api_url" {
  name  = "/georisk/${var.env_name}/pipeline/api-url"
  type  = "String"
  value = "https://${aws_apprunner_service.api.service_url}"
  tags  = { Name = "georisk-${var.env_name}-pipeline-api-url" }
}

resource "aws_ssm_parameter" "pipeline_api_key" {
  name  = "/georisk/${var.env_name}/pipeline/api-key"
  type  = "SecureString"
  value = var.api_key
  tags  = { Name = "georisk-${var.env_name}-pipeline-api-key" }
}

output "service_url" { value = aws_apprunner_service.api.service_url }
output "service_arn" { value = aws_apprunner_service.api.arn }

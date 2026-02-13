# --- Execution Role (ECR pull, CloudWatch logs) ---
resource "aws_iam_role" "execution" {
  name = "georisk-${var.env_name}-pipeline-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "georisk-${var.env_name}-pipeline-execution" }
}

resource "aws_iam_role_policy_attachment" "execution_ecr" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "execution_ssm" {
  name = "ssm-secrets"
  role = aws_iam_role.execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "ssm:GetParameters"
      Resource = [
        "${local.ssm_prefix}/georisk/${var.env_name}/pipeline/*"
      ]
    }]
  })
}

# --- Task Role (S3, Secrets Manager, API access) ---
resource "aws_iam_role" "task" {
  name = "georisk-${var.env_name}-pipeline-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "georisk-${var.env_name}-pipeline-task" }
}

resource "aws_iam_role_policy" "task_s3" {
  name = "s3-access"
  role = aws_iam_role.task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ]
      Resource = flatten([
        [for arn in var.s3_bucket_arns : arn],
        [for arn in var.s3_bucket_arns : "${arn}/*"]
      ])
    }]
  })
}

resource "aws_iam_role_policy" "task_secrets" {
  name = "secrets-access"
  role = aws_iam_role.task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "secretsmanager:GetSecretValue"
      Resource = var.rds_secret_arn
    }]
  })
}

output "cluster_arn" { value = aws_ecs_cluster.main.arn }
output "task_definition_arn" { value = aws_ecs_task_definition.pipeline.arn }
output "task_role_arn" { value = aws_iam_role.task.arn }
output "execution_role_arn" { value = aws_iam_role.execution.arn }

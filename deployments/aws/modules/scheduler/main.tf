variable "env_name" { type = string }
variable "ecs_cluster_arn" { type = string }
variable "task_definition_arn" { type = string }
variable "pipeline_task_role_arn" { type = string }
variable "pipeline_execution_role_arn" { type = string }
variable "pipeline_subnet_ids" { type = list(string) }
variable "pipeline_sg_id" { type = string }

# --- Schedule Group ---
resource "aws_scheduler_schedule_group" "main" {
  name = "georisk-schedules"

  tags = { Name = "georisk-${var.env_name}-schedules" }
}

# --- IAM Role for EventBridge Scheduler to invoke ECS RunTask ---
resource "aws_iam_role" "scheduler" {
  name = "georisk-${var.env_name}-scheduler"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "georisk-${var.env_name}-scheduler-role" }
}

resource "aws_iam_role_policy" "scheduler_ecs" {
  name = "ecs-run-task"
  role = aws_iam_role.scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "ecs:RunTask"
        Resource = var.task_definition_arn
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

# Individual schedules are created at runtime by the API via EventBridgeSchedulerService

output "scheduler_role_arn" { value = aws_iam_role.scheduler.arn }
output "schedule_group_name" { value = aws_scheduler_schedule_group.main.name }

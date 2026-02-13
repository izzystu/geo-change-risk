variable "env_name" { type = string }
variable "data_subnet_ids" { type = list(string) }
variable "rds_security_group_id" { type = string }

resource "random_password" "rds" {
  length  = 32
  special = false
}

resource "aws_db_subnet_group" "main" {
  name       = "georisk-${var.env_name}"
  subnet_ids = var.data_subnet_ids

  tags = { Name = "georisk-${var.env_name}-db-subnet" }
}

resource "aws_db_parameter_group" "postgis" {
  name   = "georisk-${var.env_name}-pg16-postgis"
  family = "postgres16"

  parameter {
    name         = "shared_preload_libraries"
    value        = "pg_stat_statements"
    apply_method = "pending-reboot"
  }

  tags = { Name = "georisk-${var.env_name}-pg-params" }
}

resource "aws_db_instance" "main" {
  identifier = "georisk-${var.env_name}"

  engine         = "postgres"
  engine_version = "16"
  instance_class = "db.t4g.micro"

  allocated_storage     = 20
  max_allocated_storage = 50
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = "georisk"
  username = "georisk"
  password = random_password.rds.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [var.rds_security_group_id]
  parameter_group_name   = aws_db_parameter_group.postgis.name

  multi_az            = false
  publicly_accessible = false
  skip_final_snapshot = true

  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "mon:04:00-mon:05:00"

  tags = { Name = "georisk-${var.env_name}" }
}

# Store credentials in Secrets Manager
resource "aws_secretsmanager_secret" "rds" {
  name                    = "georisk/${var.env_name}/rds"
  recovery_window_in_days = 0

  tags = { Name = "georisk-${var.env_name}-rds-credentials" }
}

resource "aws_secretsmanager_secret_version" "rds" {
  secret_id = aws_secretsmanager_secret.rds.id
  secret_string = jsonencode({
    username = aws_db_instance.main.username
    password = random_password.rds.result
    host     = aws_db_instance.main.address
    port     = aws_db_instance.main.port
    dbname   = aws_db_instance.main.db_name
    connection_string = "Host=${aws_db_instance.main.address};Port=${aws_db_instance.main.port};Database=${aws_db_instance.main.db_name};Username=${aws_db_instance.main.username};Password=${random_password.rds.result}"
  })
}

output "endpoint" { value = aws_db_instance.main.address }
output "db_name" { value = aws_db_instance.main.db_name }
output "credentials_secret_arn" { value = aws_secretsmanager_secret.rds.arn }

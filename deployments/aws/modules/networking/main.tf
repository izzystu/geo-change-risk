variable "env_name" { type = string }
variable "region" { type = string }

data "aws_availability_zones" "available" {
  state = "available"
}

# --- VPC ---
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "georisk-${var.env_name}" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "georisk-${var.env_name}-igw" }
}

# --- Public subnets (ECS tasks with public IP) ---
resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.${count.index + 1}.0/24"
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = { Name = "georisk-${var.env_name}-public-${count.index + 1}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "georisk-${var.env_name}-public-rt" }
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.main.id
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# --- Data subnets (RDS, private) ---
resource "aws_subnet" "data" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.${count.index + 10}.0/24"
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = { Name = "georisk-${var.env_name}-data-${count.index + 1}" }
}

# --- S3 Gateway VPC Endpoint (free) ---
resource "aws_vpc_endpoint" "s3" {
  vpc_id       = aws_vpc.main.id
  service_name = "com.amazonaws.${var.region}.s3"

  route_table_ids = [aws_route_table.public.id]

  tags = { Name = "georisk-${var.env_name}-s3-endpoint" }
}

# --- VPC Interface Endpoints (for App Runner VPC egress → AWS APIs) ---

resource "aws_security_group" "vpc_endpoints" {
  name_prefix = "georisk-${var.env_name}-endpoints-"
  description = "VPC interface endpoints"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTPS from VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]
  }

  tags = { Name = "georisk-${var.env_name}-endpoints-sg" }
}

resource "aws_vpc_endpoint" "ecs" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.region}.ecs"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [aws_subnet.data[0].id]
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true
  tags = { Name = "georisk-${var.env_name}-ecs-endpoint" }
}

resource "aws_vpc_endpoint" "scheduler" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.region}.scheduler"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [aws_subnet.data[0].id]
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true
  tags = { Name = "georisk-${var.env_name}-scheduler-endpoint" }
}

# --- Security Groups ---

resource "aws_security_group" "pipeline" {
  name_prefix = "georisk-${var.env_name}-pipeline-"
  description = "Pipeline ECS task security group"
  vpc_id      = aws_vpc.main.id

  egress {
    description     = "PostgreSQL access"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.rds.id]
  }

  egress {
    description = "HTTPS for STAC, S3, USGS APIs"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "georisk-${var.env_name}-pipeline-sg" }
}

resource "aws_security_group" "rds" {
  name_prefix = "georisk-${var.env_name}-rds-"
  description = "RDS PostgreSQL security group"
  vpc_id      = aws_vpc.main.id

  tags = { Name = "georisk-${var.env_name}-rds-sg" }
}

resource "aws_security_group_rule" "rds_from_pipeline" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.rds.id
  source_security_group_id = aws_security_group.pipeline.id
  description              = "PostgreSQL from Pipeline"
}

# --- Outputs ---
output "vpc_id" { value = aws_vpc.main.id }
output "public_subnet_ids" { value = aws_subnet.public[*].id }
output "data_subnet_ids" { value = aws_subnet.data[*].id }
output "pipeline_security_group_id" { value = aws_security_group.pipeline.id }
output "rds_security_group_id" { value = aws_security_group.rds.id }

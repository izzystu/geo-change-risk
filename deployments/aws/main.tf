terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "georisk"
      Environment = var.env_name
      ManagedBy   = "terraform"
    }
  }
}

# --- Networking ---
module "networking" {
  source   = "./modules/networking"
  env_name = var.env_name
  region   = var.region
}

# --- Database ---
module "database" {
  source              = "./modules/database"
  env_name            = var.env_name
  data_subnet_ids     = module.networking.data_subnet_ids
  rds_security_group_id = module.networking.rds_security_group_id
}

# --- S3 Storage ---
module "storage" {
  source   = "./modules/storage"
  env_name = var.env_name
}

# --- ECR Repositories ---
module "ecr" {
  source   = "./modules/ecr"
  env_name = var.env_name
}

# --- ECS Pipeline ---
module "pipeline" {
  source                = "./modules/pipeline"
  env_name              = var.env_name
  region                = var.region
  cluster_name          = "georisk-${var.env_name}"
  pipeline_ecr_repo_url = module.ecr.pipeline_repo_url
  pipeline_subnet_ids   = module.networking.public_subnet_ids
  pipeline_sg_id        = module.networking.pipeline_security_group_id
  rds_secret_arn        = module.database.credentials_secret_arn
  s3_bucket_arns        = module.storage.bucket_arns
  s3_bucket_names       = module.storage.bucket_names
}

# --- App Runner ---
module "apprunner" {
  source              = "./modules/apprunner"
  env_name            = var.env_name
  region              = var.region
  api_ecr_repo_url    = module.ecr.api_repo_url
  api_ecr_repo_arn    = module.ecr.api_repo_arn
  rds_secret_arn      = module.database.credentials_secret_arn
  rds_endpoint        = module.database.endpoint
  rds_db_name         = module.database.db_name
  s3_bucket_arns      = module.storage.bucket_arns
  s3_bucket_names     = module.storage.bucket_names
  api_key             = var.api_key
  ecs_cluster_arn     = module.pipeline.cluster_arn
  task_definition_arn = module.pipeline.task_definition_arn
  pipeline_subnet_ids = join(",", module.networking.public_subnet_ids)
  pipeline_sg_id      = module.networking.pipeline_security_group_id
  scheduler_role_arn  = module.scheduler.scheduler_role_arn
  pipeline_task_role_arn      = module.pipeline.task_role_arn
  pipeline_execution_role_arn = module.pipeline.execution_role_arn
  vpc_connector_subnets  = module.networking.public_subnet_ids
  vpc_id                 = module.networking.vpc_id
  rds_security_group_id  = module.networking.rds_security_group_id
}

# --- EventBridge Scheduler ---
module "scheduler" {
  source              = "./modules/scheduler"
  env_name            = var.env_name
  ecs_cluster_arn     = module.pipeline.cluster_arn
  task_definition_arn = module.pipeline.task_definition_arn
  pipeline_task_role_arn      = module.pipeline.task_role_arn
  pipeline_execution_role_arn = module.pipeline.execution_role_arn
  pipeline_subnet_ids = module.networking.public_subnet_ids
  pipeline_sg_id      = module.networking.pipeline_security_group_id
}

# --- CloudFront CDN ---
module "cdn" {
  source         = "./modules/cdn"
  env_name       = var.env_name
  webui_bucket   = module.storage.webui_bucket_name
  webui_bucket_arn           = module.storage.webui_bucket_arn
  webui_bucket_domain_name   = module.storage.webui_bucket_domain_name
}

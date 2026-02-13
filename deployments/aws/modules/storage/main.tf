variable "env_name" { type = string }

locals {
  buckets = {
    rasters   = "georisk-${var.env_name}-rasters"
    artifacts = "georisk-${var.env_name}-artifacts"
    imagery   = "georisk-${var.env_name}-imagery"
    changes   = "georisk-${var.env_name}-changes"
  }
}

resource "aws_s3_bucket" "data" {
  for_each = local.buckets
  bucket   = each.value

  tags = { Name = each.value }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  for_each = local.buckets
  bucket   = aws_s3_bucket.data[each.key].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "data" {
  for_each = local.buckets
  bucket   = aws_s3_bucket.data[each.key].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# CORS for presigned URL access (imagery and changes buckets)
resource "aws_s3_bucket_cors_configuration" "imagery" {
  bucket = aws_s3_bucket.data["imagery"].id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET"]
    allowed_origins = ["*"]
    max_age_seconds = 3600
  }
}

resource "aws_s3_bucket_cors_configuration" "changes" {
  bucket = aws_s3_bucket.data["changes"].id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET"]
    allowed_origins = ["*"]
    max_age_seconds = 3600
  }
}

# Lifecycle: delete rasters and artifacts after 90 days
resource "aws_s3_bucket_lifecycle_configuration" "rasters" {
  bucket = aws_s3_bucket.data["rasters"].id

  rule {
    id     = "delete-old-rasters"
    status = "Enabled"

    expiration {
      days = 90
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket = aws_s3_bucket.data["artifacts"].id

  rule {
    id     = "delete-old-artifacts"
    status = "Enabled"

    expiration {
      days = 90
    }
  }
}

# Web UI static hosting bucket
resource "aws_s3_bucket" "webui" {
  bucket = "georisk-${var.env_name}-webui"
  tags   = { Name = "georisk-${var.env_name}-webui" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "webui" {
  bucket = aws_s3_bucket.webui.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "webui" {
  bucket = aws_s3_bucket.webui.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

output "bucket_arns" {
  value = [for b in aws_s3_bucket.data : b.arn]
}

output "bucket_names" {
  value = {
    rasters   = aws_s3_bucket.data["rasters"].bucket
    artifacts = aws_s3_bucket.data["artifacts"].bucket
    imagery   = aws_s3_bucket.data["imagery"].bucket
    changes   = aws_s3_bucket.data["changes"].bucket
  }
}

output "webui_bucket_name" { value = aws_s3_bucket.webui.bucket }
output "webui_bucket_arn" { value = aws_s3_bucket.webui.arn }
output "webui_bucket_domain_name" { value = aws_s3_bucket.webui.bucket_regional_domain_name }

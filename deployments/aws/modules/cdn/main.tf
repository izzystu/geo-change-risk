variable "env_name" { type = string }
variable "webui_bucket" { type = string }
variable "webui_bucket_arn" { type = string }
variable "webui_bucket_domain_name" { type = string }

# --- Origin Access Control ---
resource "aws_cloudfront_origin_access_control" "webui" {
  name                              = "georisk-${var.env_name}-webui-oac"
  description                       = "OAC for web UI S3 bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# --- CloudFront Distribution ---
resource "aws_cloudfront_distribution" "webui" {
  enabled             = true
  default_root_object = "index.html"
  comment             = "Geo Change Risk web UI (${var.env_name})"

  origin {
    domain_name              = var.webui_bucket_domain_name
    origin_id                = "s3-webui"
    origin_access_control_id = aws_cloudfront_origin_access_control.webui.id
  }

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "s3-webui"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 86400
    max_ttl     = 31536000
  }

  # SPA fallback: route 403/404 to index.html
  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }

  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = { Name = "georisk-${var.env_name}-webui" }
}

# --- S3 Bucket Policy for CloudFront OAC ---
data "aws_caller_identity" "current" {}

resource "aws_s3_bucket_policy" "webui" {
  bucket = var.webui_bucket

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${var.webui_bucket_arn}/*"
      Condition = {
        StringEquals = {
          "AWS:SourceArn" = aws_cloudfront_distribution.webui.arn
        }
      }
    }]
  })
}

output "distribution_url" { value = aws_cloudfront_distribution.webui.domain_name }
output "distribution_id" { value = aws_cloudfront_distribution.webui.id }

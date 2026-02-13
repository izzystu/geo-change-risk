# Geo Change Risk - AWS Deployment Script
# Usage: .\deployments\aws\scripts\deploy.ps1 [-SkipBuild] [-SkipTerraform] [-SkipWebUI]
#
# Prerequisites:
#   - AWS CLI configured with credentials in ~/.aws/credentials (not SSO login)
#   - Docker Desktop running
#   - Terraform >= 1.5 installed
#   - Node.js 18+ installed
#   - .NET 8 SDK installed
#   - $env:TF_VAR_api_key set to your desired API key
#
# First-time setup:
#   1. Create ECR repos first: terraform init && terraform apply -var-file="environments\dev.tfvars" '-target=module.ecr'
#   2. Then run this script

param(
    [switch]$SkipBuild,
    [switch]$SkipTerraform,
    [switch]$SkipWebUI,
    [string]$Environment = "dev",
    [string]$Region = "us-east-1"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..") | Select-Object -ExpandProperty Path
$TerraformDir = Join-Path $RepoRoot "deployments\aws"
$ApiDir = Join-Path $RepoRoot "src\api"
$PipelineDir = Join-Path $RepoRoot "src\pipeline"
$WebUIDir = Join-Path $RepoRoot "src\web-ui"

Write-Host "`n=== Geo Change Risk - AWS Deployment ===" -ForegroundColor Cyan
Write-Host "Environment: $Environment"
Write-Host "Region: $Region"
Write-Host ""

# Verify TF_VAR_api_key is set
if (-not $env:TF_VAR_api_key) {
    Write-Error "TF_VAR_api_key environment variable is not set. Set it with: `$env:TF_VAR_api_key = 'your-key'"
    exit 1
}

# Get AWS account ID
$AccountId = aws sts get-caller-identity --query Account --output text
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to get AWS account ID. Ensure AWS CLI is configured with credentials in ~/.aws/credentials."
    exit 1
}
Write-Host "AWS Account: $AccountId"

$EcrRegistry = "$AccountId.dkr.ecr.$Region.amazonaws.com"
$ApiRepoUri = "$EcrRegistry/georisk-$Environment-api"
$PipelineRepoUri = "$EcrRegistry/georisk-$Environment-pipeline"

# --- Step 1: Build and push Docker images ---
if (-not $SkipBuild) {
    Write-Host "`n--- Building Docker Images ---" -ForegroundColor Yellow

    # Login to ECR — use --password flag (piping with --password-stdin fails on Windows PowerShell 5.x)
    Write-Host "Logging in to ECR..."
    $EcrPassword = aws ecr get-login-password --region $Region
    docker login --username AWS --password $EcrPassword $EcrRegistry
    if ($LASTEXITCODE -ne 0) {
        Write-Error "ECR login failed."
        exit 1
    }

    # Build API image
    Write-Host "Building API Docker image..."
    docker build -t georisk-api -f "$ApiDir\Dockerfile" "$ApiDir"
    docker tag georisk-api:latest "${ApiRepoUri}:latest"
    Write-Host "Pushing API image to ECR..."
    docker push "${ApiRepoUri}:latest"

    # Build Pipeline image
    Write-Host "Building Pipeline Docker image..."
    docker build -t georisk-pipeline -f "$PipelineDir\Dockerfile" "$PipelineDir"
    docker tag georisk-pipeline:latest "${PipelineRepoUri}:latest"
    Write-Host "Pushing Pipeline image to ECR..."
    docker push "${PipelineRepoUri}:latest"

    Write-Host "Docker images built and pushed." -ForegroundColor Green
}

# --- Step 2: Terraform apply ---
if (-not $SkipTerraform) {
    Write-Host "`n--- Running Terraform ---" -ForegroundColor Yellow

    Push-Location $TerraformDir
    try {
        # Check if API URL already exists from a previous deploy
        $ExistingApiUrl = ""
        try { $ExistingApiUrl = terraform output -raw api_url 2>$null } catch {}

        # Phase 1: Create/update all infrastructure
        terraform init
        terraform apply -var-file="environments\$Environment.tfvars" -var "pipeline_api_url=$ExistingApiUrl" -auto-approve

        # Read the (possibly new) API URL
        $NewApiUrl = terraform output -raw api_url

        # Phase 2: Always re-apply with the API URL to ensure the pipeline task
        # definition has the correct GEORISK_API_URL and GEORISK_API_KEY env vars
        # (these depend on both the API URL and the api_key, which may change independently)
        Write-Host "Updating pipeline task definition with API URL..." -ForegroundColor Yellow
        terraform apply -var-file="environments\$Environment.tfvars" -var "pipeline_api_url=$NewApiUrl" -auto-approve
    }
    finally {
        Pop-Location
    }

    Write-Host "Terraform apply complete." -ForegroundColor Green
}

# Get Terraform outputs
Push-Location $TerraformDir
$ApiUrl = terraform output -raw api_url
$CloudFrontUrl = terraform output -raw cloudfront_url
$WebUIBucket = terraform output -raw webui_bucket
$CloudFrontDistId = terraform output -raw cloudfront_distribution_id
Pop-Location

# --- Step 3: Build and deploy Web UI ---
if (-not $SkipWebUI) {
    Write-Host "`n--- Building Web UI ---" -ForegroundColor Yellow

    Push-Location $WebUIDir
    try {
        npm install

        # Override .env to bake in the AWS API URL (SvelteKit $env/static/public reads .env at build time)
        $EnvBackup = $null
        $EnvFile = Join-Path $WebUIDir ".env"
        if (Test-Path $EnvFile) {
            $EnvBackup = Get-Content $EnvFile -Raw
        }
        $ApiUrlClean = $ApiUrl -replace '^https?://', ''
        Set-Content $EnvFile "PUBLIC_API_URL=https://$ApiUrlClean"

        $env:ADAPTER = "static"
        npm run build

        # Restore original .env
        if ($EnvBackup) {
            Set-Content $EnvFile $EnvBackup
        }
        Remove-Item Env:ADAPTER -ErrorAction SilentlyContinue
    }
    finally {
        Pop-Location
    }

    # Upload to S3
    Write-Host "Uploading web UI to S3..."
    aws s3 sync "$WebUIDir\build" "s3://$WebUIBucket" --delete

    # Invalidate CloudFront cache
    Write-Host "Invalidating CloudFront cache..."
    aws cloudfront create-invalidation --distribution-id $CloudFrontDistId --paths "/*" | Out-Null

    Write-Host "Web UI deployed." -ForegroundColor Green
}

# --- Summary ---
Write-Host "`n=== Deployment Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Web UI:   https://$CloudFrontUrl" -ForegroundColor Cyan
Write-Host "API:      https://$ApiUrl" -ForegroundColor Cyan
Write-Host "Health:   https://$ApiUrl/health" -ForegroundColor Cyan
Write-Host ""
Write-Host "Database migrations are applied automatically by the API on startup." -ForegroundColor DarkGray
Write-Host "To load sample data: python areas-of-interest\paradise\initialize.py --api-url https://$ApiUrl" -ForegroundColor DarkGray
Write-Host ""

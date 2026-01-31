# Local Setup Scripts - Test Runbook

> **Last Updated:** 2026-01-30
> **Related Code:** `deployments/local/setup.ps1`, `deployments/local/setup.sh`
> **Estimated Time:** 15-20 minutes

## Overview

This runbook verifies the local development setup scripts work correctly across different scenarios: fresh install, existing credentials, error handling, and idempotency.

## Prerequisites

- [ ] Docker Desktop installed and running
- [ ] .NET 8 SDK installed
- [ ] PowerShell 7+ (Windows) or Bash (Linux/Mac)
- [ ] No containers named `georisk-*` running

## Important: Testing Destroys Local Data

Running these tests will remove Docker volumes, which **deletes your PostgreSQL database
and MinIO storage**. After testing, you will need to restore your environment:

1. Restore your backed-up config files (`.env`, `appsettings.Development.json`, `src/pipeline/.env`)
2. Run `docker-compose up -d` to recreate containers
3. Run database migrations (`dotnet ef database update`)
4. Re-initialize AOI data (`python initialize.py`)

### Back Up Before Testing

```bash
mkdir -p /tmp/georisk-backup
cp infra/local/.env /tmp/georisk-backup/
cp src/api/GeoChangeRisk.Api/appsettings.Development.json /tmp/georisk-backup/
cp src/pipeline/.env /tmp/georisk-backup/ 2>/dev/null
```

```powershell
New-Item -ItemType Directory -Force -Path $env:TEMP\georisk-backup
Copy-Item infra\local\.env $env:TEMP\georisk-backup\
Copy-Item src\api\GeoChangeRisk.Api\appsettings.Development.json $env:TEMP\georisk-backup\
Copy-Item src\pipeline\.env $env:TEMP\georisk-backup\ -ErrorAction SilentlyContinue
```

### Restore After Testing

```bash
docker-compose -f infra/local/docker-compose.yml down -v
cp /tmp/georisk-backup/.env infra/local/
cp /tmp/georisk-backup/appsettings.Development.json src/api/GeoChangeRisk.Api/
cp /tmp/georisk-backup/.env src/pipeline/ 2>/dev/null
docker-compose -f infra/local/docker-compose.yml up -d
# Wait for services, then:
# cd src/api/GeoChangeRisk.Data && dotnet ef database update
# cd areas-of-interest/paradise && python initialize.py
```

```powershell
docker-compose -f infra\local\docker-compose.yml down -v
Copy-Item $env:TEMP\georisk-backup\.env infra\local\
Copy-Item $env:TEMP\georisk-backup\appsettings.Development.json src\api\GeoChangeRisk.Api\
Copy-Item $env:TEMP\georisk-backup\.env src\pipeline\ -ErrorAction SilentlyContinue
docker-compose -f infra\local\docker-compose.yml up -d
# Wait for services, then:
# cd src\api\GeoChangeRisk.Data; dotnet ef database update
# cd areas-of-interest\paradise; python initialize.py
```

## Clean State Requirements

Before each test scenario, reset to a clean state:

```bash
# Stop and remove containers and volumes
docker-compose -f infra/local/docker-compose.yml down -v 2>/dev/null || true

# Remove generated config files
rm -f infra/local/.env
rm -f src/api/GeoChangeRisk.Api/appsettings.Development.json
rm -f src/pipeline/.env

# Verify clean state
docker ps -a | grep georisk  # Should return nothing
ls infra/local/.env 2>/dev/null  # Should fail (file not found)
```

PowerShell equivalent:
```powershell
# Stop and remove containers and volumes
docker-compose -f infra/local/docker-compose.yml down -v 2>$null

# Remove generated config files
Remove-Item infra/local/.env -ErrorAction SilentlyContinue
Remove-Item src/api/GeoChangeRisk.Api\appsettings.Development.json -ErrorAction SilentlyContinue
Remove-Item src\pipeline\.env -ErrorAction SilentlyContinue

# Verify clean state
docker ps -a | Select-String georisk  # Should return nothing
Test-Path infra/local/.env  # Should return False
```

## Test Matrix

| Test ID | Scenario | Flags | Expected Result |
|---------|----------|-------|-----------------|
| T1 | Fresh install (default) | (none) | Generates credentials, app configs, starts services |
| T2 | Fresh install with skip-env | `--skip-env` | Fails with helpful error message |
| T3 | Existing .env file | (none) | Preserves .env, generates app configs from it |
| T4 | Custom credentials | `--skip-env` | App configs use custom credentials |
| T5 | Idempotency | Run twice | Second run succeeds, all configs preserved |
| T6 | Force recreation | `--force` | Recreates containers, preserves configs |
| T7 | Help flag | `--help` | Shows usage, exits cleanly |
| T8 | Skip prerequisites | `--skip-prerequisites` | Skips checks, continues setup |

---

## Test Procedures

### T1: Fresh Install (Default)

**Scenario:** New developer clones repo and runs setup with no prior configuration.

**Clean State:** Remove `.env` and all containers (see above)

**Steps:**
1. Run the setup script:
   ```bash
   ./deployments/local/setup.sh
   ```
   ```powershell
   .\deployments\local\setup.ps1
   ```

2. Observe the output

**Expected Result:**
- [ ] Script outputs "Generating .env with random credentials..."
- [ ] Script outputs "Generated infra/local/.env with random credentials"
- [ ] Script outputs "Generated .../appsettings.Development.json"
- [ ] Script outputs "Generated .../src/pipeline/.env"
- [ ] All prerequisite checks pass (or warn for optional items)
- [ ] Docker containers start successfully
- [ ] Services become healthy within 60 seconds
- [ ] MinIO buckets are created
- [ ] Summary shows randomly generated passwords (24 characters, alphanumeric)
- [ ] PostgreSQL password differs from MinIO password

**Verification:**
```bash
# Check .env was created with passwords
grep "POSTGRES_PASSWORD=" infra/local/.env | grep -v "^#"  # Should show 24-char password
grep "MINIO_ROOT_PASSWORD=" infra/local/.env | grep -v "^#"  # Should show different 24-char password

# Check app config files were generated with matching credentials
cat src/api/GeoChangeRisk.Api/appsettings.Development.json  # Should contain connection string with generated PG password
cat src/pipeline/.env  # Should contain MINIO_SECRET_KEY with generated MinIO password

# Check containers are running
docker ps | grep georisk-postgres  # Should show healthy
docker ps | grep georisk-minio     # Should show healthy

# Check MinIO buckets exist
docker exec georisk-minio mc ls local/  # Should list geo-rasters, geo-artifacts, ml-models
```

```powershell
# Check .env was created with passwords
Select-String "POSTGRES_PASSWORD=" infra\local\.env  # Should show 24-char password
Select-String "MINIO_ROOT_PASSWORD=" infra\local\.env  # Should show different 24-char password

# Check app config files were generated with matching credentials
Get-Content src\api\GeoChangeRisk.Api\appsettings.Development.json  # Should contain connection string with generated PG password
Get-Content src\pipeline\.env  # Should contain MINIO_SECRET_KEY with generated MinIO password

# Check containers are running
docker ps | Select-String georisk-postgres  # Should show healthy
docker ps | Select-String georisk-minio     # Should show healthy

# Check MinIO buckets exist
docker exec georisk-minio mc ls local/  # Should list geo-rasters, geo-artifacts, ml-models
```

---

### T2: Fresh Install with --skip-env (Should Fail)

**Scenario:** Developer tries to skip env generation but no .env exists.

**Clean State:** Remove `.env` file only (containers can remain)

**Steps:**
1. Ensure no .env file exists:
   ```bash
   rm -f infra/local/.env
   ```
   ```powershell
   Remove-Item infra\local\.env -ErrorAction SilentlyContinue
   ```

2. Run setup with skip flag:
   ```bash
   ./deployments/local/setup.sh --skip-env
   ```
   ```powershell
   .\deployments\local\setup.ps1 -SkipEnv
   ```

**Expected Result:**
- [ ] Script outputs error: "No .env file found"
- [ ] Script outputs hint about creating from .env.example
- [ ] Script exits with non-zero status
- [ ] No containers are started/modified

**Verification:**
```bash
echo $?  # Should be non-zero (1)
```

```powershell
$LASTEXITCODE  # Should be non-zero (1)
```

---

### T3: Existing .env File (Preserve Credentials)

**Scenario:** Developer already has .env file, runs setup again.

**Setup:**
```bash
# Create .env with known test values
cat > infra/local/.env << 'EOF'
POSTGRES_USER=testuser
POSTGRES_PASSWORD=testpassword123
POSTGRES_DB=testdb
POSTGRES_PORT=5432
MINIO_ROOT_USER=testminio
MINIO_ROOT_PASSWORD=testminiopass456
MINIO_API_PORT=9000
MINIO_CONSOLE_PORT=9001
API_PORT=5074
WEB_UI_PORT=5173
EOF
```

```powershell
# Create .env with known test values
@"
POSTGRES_USER=testuser
POSTGRES_PASSWORD=testpassword123
POSTGRES_DB=testdb
POSTGRES_PORT=5432
MINIO_ROOT_USER=testminio
MINIO_ROOT_PASSWORD=testminiopass456
MINIO_API_PORT=9000
MINIO_CONSOLE_PORT=9001
API_PORT=5074
WEB_UI_PORT=5173
"@ | Set-Content infra\local\.env -Encoding UTF8
```

**Steps:**
1. Run setup script (no flags):
   ```bash
   ./deployments/local/setup.sh
   ```
   ```powershell
   .\deployments\local\setup.ps1
   ```

**Expected Result:**
- [ ] Script outputs ".env file already exists (keeping existing credentials)"
- [ ] Script does NOT output "Generating .env"
- [ ] Original credentials are preserved in .env file
- [ ] App config files are generated from the existing .env credentials
- [ ] Summary shows the test credentials (testuser/testpassword123)

**Verification:**
```bash
grep "POSTGRES_PASSWORD=testpassword123" infra/local/.env  # Should match
grep "MINIO_ROOT_PASSWORD=testminiopass456" infra/local/.env  # Should match

# App configs should use the test credentials
grep "testpassword123" src/api/GeoChangeRisk.Api/appsettings.Development.json  # Should match
grep "testminiopass456" src/pipeline/.env  # Should match
```

```powershell
Select-String "POSTGRES_PASSWORD=testpassword123" infra\local\.env  # Should match
Select-String "MINIO_ROOT_PASSWORD=testminiopass456" infra\local\.env  # Should match

# App configs should use the test credentials
Select-String "testpassword123" src\api\GeoChangeRisk.Api\appsettings.Development.json  # Should match
Select-String "testminiopass456" src\pipeline\.env  # Should match
```

---

### T4: Custom Credentials with --skip-env

**Scenario:** Developer has existing PostgreSQL/MinIO and provides their own credentials.

**Setup:**
```bash
# Remove app config files so they get regenerated from custom .env
rm -f src/api/GeoChangeRisk.Api/appsettings.Development.json
rm -f src/pipeline/.env

# Create .env with custom port to simulate existing services
cat > infra/local/.env << 'EOF'
POSTGRES_USER=myexistinguser
POSTGRES_PASSWORD=myexistingpass
POSTGRES_DB=georisk
POSTGRES_PORT=5433
MINIO_ROOT_USER=myminio
MINIO_ROOT_PASSWORD=myminiopass
MINIO_API_PORT=9002
MINIO_CONSOLE_PORT=9003
API_PORT=5074
WEB_UI_PORT=5173
EOF
```

```powershell
# Remove app config files so they get regenerated from custom .env
Remove-Item src\api\GeoChangeRisk.Api\appsettings.Development.json -ErrorAction SilentlyContinue
Remove-Item src\pipeline\.env -ErrorAction SilentlyContinue

# Create .env with custom port to simulate existing services
@"
POSTGRES_USER=myexistinguser
POSTGRES_PASSWORD=myexistingpass
POSTGRES_DB=georisk
POSTGRES_PORT=5433
MINIO_ROOT_USER=myminio
MINIO_ROOT_PASSWORD=myminiopass
MINIO_API_PORT=9002
MINIO_CONSOLE_PORT=9003
API_PORT=5074
WEB_UI_PORT=5173
"@ | Set-Content infra\local\.env -Encoding UTF8
```

**Steps:**
1. Run setup with skip-env flag:
   ```bash
   ./deployments/local/setup.sh --skip-env
   ```
   ```powershell
   .\deployments\local\setup.ps1 -SkipEnv
   ```

**Expected Result:**
- [ ] Script outputs "Using existing .env file"
- [ ] App config files are generated from custom credentials
- [ ] Docker containers start on custom ports (5433, 9002, 9003)
- [ ] Summary shows the custom credentials

**Verification:**
```bash
docker ps | grep "5433->5432"  # PostgreSQL on custom port
docker ps | grep "9002->9000"  # MinIO API on custom port

# App configs should use the custom credentials
grep "myexistingpass" src/api/GeoChangeRisk.Api/appsettings.Development.json  # Should match
grep "myminiopass" src/pipeline/.env  # Should match
grep "9002" src/pipeline/.env  # Should show custom port
```

```powershell
docker ps | Select-String "5433->5432"  # PostgreSQL on custom port
docker ps | Select-String "9002->9000"  # MinIO API on custom port

# App configs should use the custom credentials
Select-String "myexistingpass" src\api\GeoChangeRisk.Api\appsettings.Development.json  # Should match
Select-String "myminiopass" src\pipeline\.env  # Should match
Select-String "9002" src\pipeline\.env  # Should show custom port
```

---

### T5: Idempotency (Run Twice)

**Scenario:** Setup is run twice in a row - should be safe and produce same result.

**Setup:** Complete T1 first (fresh install)

**Steps:**
1. Run setup again (same command as T1):
   ```bash
   ./deployments/local/setup.sh
   ```
   ```powershell
   .\deployments\local\setup.ps1
   ```

**Expected Result:**
- [ ] Script completes successfully (exit code 0)
- [ ] Script outputs ".env file already exists"
- [ ] Script outputs "appsettings.Development.json already exists"
- [ ] Script outputs "Pipeline .env already exists"
- [ ] Containers remain running (not recreated)
- [ ] Credentials unchanged from first run
- [ ] Buckets report "already exists"

**Verification:**
```bash
# Container uptime should be > 0 (not just created)
docker ps --format "{{.Names}} {{.Status}}" | grep georisk
```

```powershell
# Container uptime should be > 0 (not just created)
docker ps --format "{{.Names}} {{.Status}}" | Select-String georisk
```

---

### T6: Force Recreation

**Scenario:** Developer wants to start fresh, recreating all containers.

**Setup:** Have containers running from previous test

**Steps:**
1. Note current container IDs:
   ```
   docker ps -q --filter "name=georisk"
   ```

2. Run setup with force flag:
   ```bash
   ./deployments/local/setup.sh --force
   ```
   ```powershell
   .\deployments\local\setup.ps1 -Force
   ```

3. Note new container IDs

**Expected Result:**
- [ ] Script outputs "Force flag set - recreating containers..."
- [ ] Old containers are removed
- [ ] New containers are created (different IDs)
- [ ] All services healthy after recreation
- [ ] .env file is NOT regenerated (credentials preserved)

---

### T7: Help Flag

**Scenario:** Developer wants to see available options.

**Steps:**
1. Run with help flag:
   ```bash
   ./deployments/local/setup.sh --help
   ```
   ```powershell
   .\deployments\local\setup.ps1 -Help
   ```

**Expected Result:**
- [ ] Shows usage information
- [ ] Lists all available flags with descriptions
- [ ] Shows "Using existing credentials" section
- [ ] Exits with code 0
- [ ] Does NOT start any containers or modify files

---

### T8: Skip Prerequisites

**Scenario:** Developer knows prerequisites are met, wants faster setup.

**Steps:**
1. Run with skip flag:
   ```bash
   ./deployments/local/setup.sh --skip-prerequisites
   ```
   ```powershell
   .\deployments\local\setup.ps1 -SkipPrerequisites
   ```

**Expected Result:**
- [ ] No prerequisite checks are performed
- [ ] No "Checking prerequisites" output
- [ ] Setup continues directly to .env generation
- [ ] Rest of setup proceeds normally

---

## Checklist Summary

Copy this section into a GitHub issue for tracking:

```markdown
## Local Setup Scripts - Test Execution

**Tester:** @username
**Date:** YYYY-MM-DD
**Platform:** Windows / macOS / Linux
**Script:** setup.ps1 / setup.sh

### Results

- [ ] T1: Fresh install (default)
- [ ] T2: Fresh install with --skip-env (should fail)
- [ ] T3: Existing .env file preserved
- [ ] T4: Custom credentials with --skip-env
- [ ] T5: Idempotency (run twice)
- [ ] T6: Force recreation
- [ ] T7: Help flag
- [ ] T8: Skip prerequisites

### Notes

(Record any failures, unexpected behavior, or environment details)

### Environment Details
- OS Version:
- Docker Version:
- PowerShell/Bash Version:
```

---

## Troubleshooting

### Containers fail to start

**Symptom:** Docker compose fails or containers exit immediately
**Cause:** Port conflicts with existing services
**Solution:** Check for existing PostgreSQL/MinIO on default ports:
```bash
lsof -i :5432  # Check PostgreSQL port
lsof -i :9000  # Check MinIO port
```

```powershell
netstat -ano | Select-String ":5432"  # Check PostgreSQL port
netstat -ano | Select-String ":9000"  # Check MinIO port
```

### Health checks timeout

**Symptom:** Script waits 60s then reports services unhealthy
**Cause:** Slow Docker startup or resource constraints
**Solution:** Check Docker resources, try `--force` to recreate

### Permission denied on .env

**Symptom:** Cannot create or read .env file
**Cause:** File permissions or Docker volume mount issues
**Solution:** Check file ownership and permissions:
```bash
ls -la infra/local/.env
```

```powershell
Get-Acl infra\local\.env | Format-List
```

### Database connection timeout (Windows)

**Symptom:** `dotnet ef database update` or `dotnet run` fails with `Npgsql.NpgsqlException: Exception while reading from stream` / `Timeout during reading attempt`
**Cause:** WSL forwards port 5432 via `wslrelay.exe`, which binds to `[::1]:5432` (IPv6 localhost). When Npgsql connects to `localhost`, it may resolve to IPv6 first, hitting the WSL relay instead of the Docker container. The WSL PostgreSQL has different credentials, causing an authentication timeout.
**Diagnosis:** Check for multiple listeners on port 5432:
```powershell
netstat -ano | Select-String ":5432"
# If you see two different PIDs listening, the lower one on [::1] is likely wslrelay.exe
Get-Process -Id <PID> | Select-Object ProcessName, Path
```
**Solution (immediate):** Kill the WSL relay process:
```powershell
# Replace <PID> with the wslrelay.exe PID from netstat output
Stop-Process -Id <PID> -Force
```
**Solution (permanent):** Disable the PostgreSQL service inside your WSL distro so it doesn't auto-start:
```bash
wsl -e sudo systemctl disable postgresql
```

### Generated passwords contain special characters

**Symptom:** Services fail to authenticate
**Cause:** Should not happen (passwords are alphanumeric only)
**Solution:** Verify password generation:
```bash
grep PASSWORD infra/local/.env  # Should be A-Za-z0-9 only
```

```powershell
Select-String "PASSWORD" infra\local\.env  # Should be A-Za-z0-9 only
```

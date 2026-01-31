# Local Deployment

This folder contains scripts and configuration for local development deployment.

## Quick Start

### Windows (PowerShell)
```powershell
.\setup.ps1
```

### Linux/Mac (Bash)
```bash
chmod +x setup.sh
./setup.sh
```

## What the Setup Script Does

1. **Checks Prerequisites**
   - Docker (must be running)
   - .NET 8 SDK
   - Python 3.11+ (for AOI scripts)
   - Node.js 18+ (for Web UI)

2. **Generates Environment File**
   - Creates `infra/local/.env` with randomly generated passwords
   - Each developer gets unique local credentials
   - Existing `.env` files are preserved (not overwritten)

3. **Starts Infrastructure**
   - PostgreSQL 16 with PostGIS 3.4
   - MinIO (S3-compatible object storage)

4. **Waits for Health Checks**
   - Ensures services are ready before proceeding

5. **Creates MinIO Buckets**
   - `geo-rasters` - Raster imagery and processing outputs
   - `geo-artifacts` - Pipeline artifacts and provenance
   - `ml-models` - Machine learning model weights

## Services

| Service | Port | URL |
|---------|------|-----|
| PostgreSQL/PostGIS | 5432 | `localhost:5432` |
| MinIO API | 9000 | `localhost:9000` |
| MinIO Console | 9001 | http://localhost:9001 |

## Credentials

Passwords are **randomly generated** when you run the setup script. View your credentials:

```bash
# Check your generated credentials
cat infra/local/.env
```

| Service | Username | Password |
|---------|----------|----------|
| PostgreSQL | `gis` | Auto-generated (see `.env`) |
| MinIO | `minioadmin` | Auto-generated (see `.env`) |

The setup script displays credentials at the end of execution.

## Configuration Files

- `config.yaml` - Deployment configuration (ports, buckets, features)
- `../infra/local/.env` - Environment variables (secrets, connection strings)
- `../infra/local/docker-compose.yml` - Docker service definitions

## Command Line Options

### PowerShell
```powershell
.\setup.ps1 -Help              # Show help
.\setup.ps1 -SkipPrerequisites # Skip prerequisite checks
.\setup.ps1 -SkipEnv           # Use existing .env file (don't generate)
.\setup.ps1 -Force             # Force recreate containers
```

### Bash
```bash
./setup.sh --help              # Show help
./setup.sh --skip-prerequisites # Skip prerequisite checks
./setup.sh --skip-env          # Use existing .env file (don't generate)
./setup.sh --force             # Force recreate containers
```

## Using Existing Credentials

If you already have PostgreSQL or MinIO running, or want to use specific credentials:

1. Copy the example file:
   ```bash
   cp infra/local/.env.example infra/local/.env
   ```

2. Edit `infra/local/.env` with your credentials:
   ```bash
   POSTGRES_USER=your_user
   POSTGRES_PASSWORD=your_password
   POSTGRES_PORT=5433          # Different port if 5432 is in use

   MINIO_ROOT_USER=your_minio_user
   MINIO_ROOT_PASSWORD=your_minio_password
   MINIO_API_PORT=9002         # Different port if 9000 is in use
   ```

3. Run setup with the skip flag:
   ```powershell
   .\setup.ps1 -SkipEnv
   ```
   ```bash
   ./setup.sh --skip-env
   ```

## Stopping Services

```bash
docker-compose -f infra/local/docker-compose.yml down
```

To also remove volumes (all data):
```bash
docker-compose -f infra/local/docker-compose.yml down -v
```

## Viewing Logs

```bash
docker-compose -f infra/local/docker-compose.yml logs -f
docker-compose -f infra/local/docker-compose.yml logs -f postgres
docker-compose -f infra/local/docker-compose.yml logs -f minio
```

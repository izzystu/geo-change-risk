-- Geo Change Risk Platform - PostgreSQL/PostGIS Initialization
-- This script runs automatically when the container is first created

-- Enable PostGIS extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- Verify installation
SELECT PostGIS_Version();

-- Create schema for application tables (optional, EF Core will create tables)
-- CREATE SCHEMA IF NOT EXISTS georisk;

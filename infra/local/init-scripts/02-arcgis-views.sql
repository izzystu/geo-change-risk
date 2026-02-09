-- Geo Change Risk Platform - ArcGIS Pro Compatibility Views
-- Creates read-only views with lowercase column names, explicitly typed geometry
-- columns named "shape", and no jsonb fields — required for ArcGIS Pro's PostGIS driver.
--
-- These views are safe to run at any time (CREATE OR REPLACE) and do not modify
-- the application schema. They query the live tables so data is always current.
--
-- NOTE: This script runs on first container creation only (Docker entrypoint).
-- If you add it after initial setup, run it manually:
--   docker exec georisk-postgres psql -U gis -d georisk -f /docker-entrypoint-initdb.d/02-arcgis-views.sql
-- Or, if the tables don't exist yet (fresh DB), the views will fail harmlessly
-- and you can re-run the script after EF Core migrations have created the tables.

-- Areas of Interest (polygon boundaries)
CREATE OR REPLACE VIEW public.v_areas_of_interest AS
SELECT "AoiId" AS aoiid,
       "Name" AS name,
       "Description" AS description,
       "ProcessingSchedule" AS processingschedule,
       "MaxCloudCover" AS maxcloudcover,
       "ProcessingEnabled" AS processingenabled,
       "BoundingBox"::geometry(Polygon, 4326) AS shape
FROM public."AreasOfInterest";

-- Assets split by geometry type (ArcGIS Pro cannot display mixed-geometry layers)

CREATE OR REPLACE VIEW public.v_asset_polygons AS
SELECT "AssetId" AS assetid,
       "AoiId" AS aoiid,
       "Name" AS name,
       "AssetType" AS assettype,
       "Criticality" AS criticality,
       "SourceDataset" AS sourcedataset,
       "SourceFeatureId" AS sourcefeatureid,
       ST_SetSRID(ST_Force2D(ST_GeomFromWKB(ST_AsBinary("Geometry"))), 4326)::geometry(Polygon, 4326) AS shape
FROM public."Assets"
WHERE ST_GeometryType("Geometry") = 'ST_Polygon';

CREATE OR REPLACE VIEW public.v_asset_lines AS
SELECT "AssetId" AS assetid,
       "AoiId" AS aoiid,
       "Name" AS name,
       "AssetType" AS assettype,
       "Criticality" AS criticality,
       "SourceDataset" AS sourcedataset,
       "SourceFeatureId" AS sourcefeatureid,
       ST_SetSRID(ST_Force2D(ST_GeomFromWKB(ST_AsBinary("Geometry"))), 4326)::geometry(LineString, 4326) AS shape
FROM public."Assets"
WHERE ST_GeometryType("Geometry") = 'ST_LineString';

CREATE OR REPLACE VIEW public.v_asset_points AS
SELECT "AssetId" AS assetid,
       "AoiId" AS aoiid,
       "Name" AS name,
       "AssetType" AS assettype,
       "Criticality" AS criticality,
       "SourceDataset" AS sourcedataset,
       "SourceFeatureId" AS sourcefeatureid,
       ST_SetSRID(ST_Force2D(ST_GeomFromWKB(ST_AsBinary("Geometry"))), 4326)::geometry(Point, 4326) AS shape
FROM public."Assets"
WHERE ST_GeometryType("Geometry") = 'ST_Point';

-- Change polygons (detected vegetation/land-surface changes)
CREATE OR REPLACE VIEW public.v_change_polygons AS
SELECT "ChangePolygonId" AS changepolygonid,
       "RunId" AS runid,
       "AreaSqMeters" AS areasqmeters,
       "NdviDropMean" AS ndvidropmean,
       "NdviDropMax" AS ndvidropmax,
       "ChangeType" AS changetype,
       "SlopeDegreeMean" AS slopedegreemean,
       "MlConfidence" AS mlconfidence,
       "MlModelVersion" AS mlmodelversion,
       "DetectedAt" AS detectedat,
       "Geometry"::geometry(Polygon, 4326) AS shape
FROM public."ChangePolygons";

-- Risk events joined to change polygon geometry (RiskEvents has no geometry of its own)
CREATE OR REPLACE VIEW public.v_risk_events AS
SELECT r."RiskEventId" AS riskeventid,
       r."RiskScore" AS riskscore,
       r."RiskLevel" AS risklevel,
       r."DistanceMeters" AS distancemeters,
       r."AssetId" AS assetid,
       c."NdviDropMean" AS ndvidropmean,
       c."ChangeType" AS changetype,
       c."Geometry"::geometry(Polygon, 4326) AS shape
FROM public."RiskEvents" r
JOIN public."ChangePolygons" c ON r."ChangePolygonId" = c."ChangePolygonId";

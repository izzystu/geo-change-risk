# ArcGIS Pro Integration

The PostGIS database includes read-only views designed for ArcGIS Pro compatibility. The application schema uses mixed-case column names, generic geometry types, and jsonb fields that ArcGIS Pro's PostgreSQL driver cannot handle directly. The views translate these into ArcGIS-friendly equivalents: lowercase column names, explicitly typed geometry columns named `shape`, no jsonb, and mixed-geometry tables split by type.

## Setup

The views are created automatically on first database startup via `infra/local/init-scripts/02-arcgis-views.sql`. If the database already exists, run the script manually:

```bash
docker exec georisk-postgres psql -U gis -d georisk -f /docker-entrypoint-initdb.d/02-arcgis-views.sql
```

## Connecting ArcGIS Pro

1. **Catalog** pane > right-click **Databases** > **New Database Connection**
2. Database Platform: **PostgreSQL**, Instance: `localhost`, Database: `georisk`, User: `gis`, Password: (from `infra/local/.env`)
3. Expand the connection — the `v_*` views appear as feature classes. Drag them onto your map.

## Available Views

| View | Geometry | Source | Description |
|------|----------|--------|-------------|
| `v_areas_of_interest` | Polygon | AreasOfInterest | AOI bounding boxes |
| `v_asset_polygons` | Polygon | Assets | Buildings and other polygon assets |
| `v_asset_lines` | LineString | Assets | Power lines, roads |
| `v_asset_points` | Point | Assets | Substations, hospitals, schools, power poles |
| `v_change_polygons` | Polygon | ChangePolygons | Detected vegetation/land-surface changes |
| `v_risk_events` | Polygon | RiskEvents + ChangePolygons | Risk scores with change polygon geometry |

## Why Views Are Needed

ArcGIS Pro's PostgreSQL/PostGIS driver has several constraints that don't align with the application schema created by EF Core + NetTopologySuite:

- **Column name casing:** ArcGIS Pro strips double quotes from SQL identifiers, causing PostgreSQL to lowercase them. The application uses PascalCase names (e.g., `"AssetId"`) which become the nonexistent `assetid` without quotes. Views alias all columns to lowercase.
- **Mixed geometry columns:** The `Assets` table stores Points, LineStrings, and Polygons in a single generic `geometry` column. ArcGIS Pro requires one geometry type per layer, so the views split assets into three layers filtered by `ST_GeometryType()`.
- **Generic geometry type:** The `Assets.Geometry` column is registered as generic `GEOMETRY` in the PostGIS catalog rather than a specific type like `POLYGON`. Views cast to explicit types so ArcGIS Pro can discover them as proper feature classes.
- **jsonb columns:** The `Properties` (Assets) and `Metadata` (ProcessingRuns) jsonb columns cause attribute conversion errors. Views exclude these fields.
- **Non-spatial tables:** `RiskEvents` has no geometry column. The `v_risk_events` view joins to `ChangePolygons` to provide the change polygon geometry for spatial display.

## Default Schema

When creating the database connection, ArcGIS Pro may default to the `hangfire` schema (used by the API's background job system). If you only see Hangfire tables when expanding the connection, scroll down — the `public` schema views should appear further in the list prefixed with `public.v_*`.

## Enum Reference

Some view columns contain integer enum values. Use these mappings for symbology and labeling:

**AssetType:** 0 = PowerLine, 1 = Substation, 2 = Hospital, 3 = Building, 4 = School, 5 = Road, 6 = TransmissionLine, 7 = FireStation

**Criticality:** 0 = Low, 1 = Medium, 2 = High, 3 = Critical

**RiskLevel:** 0 = Low, 1 = Medium, 2 = High, 3 = Critical

**ChangeType:** 0 = Unknown, 1 = VegetationLoss, 2 = Water, 3 = Urban

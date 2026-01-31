using GeoChangeRisk.Data.Models;
using Microsoft.EntityFrameworkCore;

namespace GeoChangeRisk.Data;

/// <summary>
/// Entity Framework Core database context for the Geo Change Risk platform.
/// Configured for PostgreSQL with PostGIS spatial support.
/// </summary>
public class GeoChangeDbContext : DbContext
{
    public GeoChangeDbContext(DbContextOptions<GeoChangeDbContext> options)
        : base(options)
    {
    }

    /// <summary>
    /// Areas of Interest - geographic regions being monitored.
    /// </summary>
    public DbSet<AreaOfInterest> AreasOfInterest => Set<AreaOfInterest>();

    /// <summary>
    /// Assets - infrastructure objects within AOIs.
    /// </summary>
    public DbSet<Asset> Assets => Set<Asset>();

    /// <summary>
    /// Processing runs - raster pipeline executions.
    /// </summary>
    public DbSet<ProcessingRun> ProcessingRuns => Set<ProcessingRun>();

    /// <summary>
    /// Change polygons - detected land-surface changes.
    /// </summary>
    public DbSet<ChangePolygon> ChangePolygons => Set<ChangePolygon>();

    /// <summary>
    /// Risk events - changes affecting assets.
    /// </summary>
    public DbSet<RiskEvent> RiskEvents => Set<RiskEvent>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        // Configure AreaOfInterest entity
        modelBuilder.Entity<AreaOfInterest>(entity =>
        {
            entity.ToTable("AreasOfInterest");
            entity.HasKey(e => e.AoiId);

            entity.Property(e => e.AoiId)
                .HasMaxLength(100);

            entity.Property(e => e.Name)
                .IsRequired()
                .HasMaxLength(200);

            entity.Property(e => e.Description)
                .HasMaxLength(2000);

            // Spatial columns with GIST index for fast queries
            entity.Property(e => e.BoundingBox)
                .HasColumnType("geometry(Polygon, 4326)");
            entity.HasIndex(e => e.BoundingBox)
                .HasMethod("gist");

            entity.Property(e => e.CenterPoint)
                .HasColumnType("geometry(Point, 4326)");

            entity.Property(e => e.CreatedAt)
                .HasDefaultValueSql("CURRENT_TIMESTAMP");

            // One-to-many relationship with Assets
            entity.HasMany(e => e.Assets)
                .WithOne(a => a.AreaOfInterest)
                .HasForeignKey(a => a.AoiId)
                .OnDelete(DeleteBehavior.Cascade);

            // Scheduling fields
            entity.Property(e => e.ProcessingSchedule)
                .HasMaxLength(50);
        });

        // Configure Asset entity
        modelBuilder.Entity<Asset>(entity =>
        {
            entity.ToTable("Assets");
            entity.HasKey(e => e.AssetId);

            entity.Property(e => e.AssetId)
                .HasMaxLength(100);

            entity.Property(e => e.AoiId)
                .IsRequired()
                .HasMaxLength(100);

            entity.Property(e => e.Name)
                .IsRequired()
                .HasMaxLength(500);

            entity.Property(e => e.AssetType)
                .HasConversion<int>();

            entity.Property(e => e.Criticality)
                .HasConversion<int>();
            // Note: Default value is set in C# model (Criticality.Medium), not database
            // This avoids EF Core sentinel value issues with enum defaults

            // Spatial column with GIST index
            entity.Property(e => e.Geometry)
                .HasColumnType("geometry(Geometry, 4326)");
            entity.HasIndex(e => e.Geometry)
                .HasMethod("gist");

            // JSONB for flexible properties
            entity.Property(e => e.Properties)
                .HasColumnType("jsonb");

            entity.Property(e => e.SourceDataset)
                .HasMaxLength(100);

            entity.Property(e => e.SourceFeatureId)
                .HasMaxLength(200);

            entity.Property(e => e.CreatedAt)
                .HasDefaultValueSql("CURRENT_TIMESTAMP");

            // Index for filtering by AOI and type
            entity.HasIndex(e => e.AoiId);
            entity.HasIndex(e => e.AssetType);
            entity.HasIndex(e => new { e.AoiId, e.AssetType });
        });

        // Configure ProcessingRun entity
        modelBuilder.Entity<ProcessingRun>(entity =>
        {
            entity.ToTable("ProcessingRuns");
            entity.HasKey(e => e.RunId);

            entity.Property(e => e.RunId)
                .HasDefaultValueSql("gen_random_uuid()");

            entity.Property(e => e.AoiId)
                .IsRequired()
                .HasMaxLength(100);

            entity.Property(e => e.Status)
                .HasConversion<int>();

            entity.Property(e => e.BeforeSceneId)
                .HasMaxLength(500);

            entity.Property(e => e.AfterSceneId)
                .HasMaxLength(500);

            entity.Property(e => e.ErrorMessage)
                .HasMaxLength(4000);

            entity.Property(e => e.Metadata)
                .HasColumnType("jsonb");

            entity.Property(e => e.CreatedAt)
                .HasDefaultValueSql("CURRENT_TIMESTAMP");

            // Relationship with AOI
            entity.HasOne(e => e.AreaOfInterest)
                .WithMany(a => a.ProcessingRuns)
                .HasForeignKey(e => e.AoiId)
                .OnDelete(DeleteBehavior.Cascade);

            // Indexes
            entity.HasIndex(e => e.AoiId);
            entity.HasIndex(e => e.Status);
            entity.HasIndex(e => new { e.AoiId, e.Status });
        });

        // Configure ChangePolygon entity
        modelBuilder.Entity<ChangePolygon>(entity =>
        {
            entity.ToTable("ChangePolygons");
            entity.HasKey(e => e.ChangePolygonId);

            entity.Property(e => e.ChangePolygonId)
                .HasDefaultValueSql("gen_random_uuid()");

            // Spatial column with GIST index
            entity.Property(e => e.Geometry)
                .HasColumnType("geometry(Polygon, 4326)");
            entity.HasIndex(e => e.Geometry)
                .HasMethod("gist");

            entity.Property(e => e.ChangeType)
                .HasConversion<int>();

            entity.Property(e => e.MlModelVersion)
                .HasMaxLength(100);

            entity.Property(e => e.DetectedAt)
                .HasDefaultValueSql("CURRENT_TIMESTAMP");

            // Relationship with ProcessingRun
            entity.HasOne(e => e.ProcessingRun)
                .WithMany(r => r.ChangePolygons)
                .HasForeignKey(e => e.RunId)
                .OnDelete(DeleteBehavior.Cascade);

            // Indexes
            entity.HasIndex(e => e.RunId);
            entity.HasIndex(e => e.ChangeType);
        });

        // Configure RiskEvent entity
        modelBuilder.Entity<RiskEvent>(entity =>
        {
            entity.ToTable("RiskEvents");
            entity.HasKey(e => e.RiskEventId);

            entity.Property(e => e.RiskEventId)
                .HasDefaultValueSql("gen_random_uuid()");

            entity.Property(e => e.AssetId)
                .IsRequired()
                .HasMaxLength(100);

            entity.Property(e => e.RiskLevel)
                .HasConversion<int>();

            entity.Property(e => e.ScoringFactors)
                .HasColumnType("jsonb");

            entity.Property(e => e.AcknowledgedBy)
                .HasMaxLength(200);

            entity.Property(e => e.CreatedAt)
                .HasDefaultValueSql("CURRENT_TIMESTAMP");

            // Relationship with ChangePolygon
            entity.HasOne(e => e.ChangePolygon)
                .WithMany(c => c.RiskEvents)
                .HasForeignKey(e => e.ChangePolygonId)
                .OnDelete(DeleteBehavior.Cascade);

            // Relationship with Asset
            entity.HasOne(e => e.Asset)
                .WithMany(a => a.RiskEvents)
                .HasForeignKey(e => e.AssetId)
                .OnDelete(DeleteBehavior.Cascade);

            // Indexes
            entity.HasIndex(e => e.ChangePolygonId);
            entity.HasIndex(e => e.AssetId);
            entity.HasIndex(e => e.RiskLevel);
            entity.HasIndex(e => e.RiskScore);
            entity.HasIndex(e => new { e.AssetId, e.RiskLevel });
        });
    }
}

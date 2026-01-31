using System.Text.Json;
using GeoChangeRisk.Data;
using GeoChangeRisk.Data.Models;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage.ValueConversion;

namespace GeoChangeRisk.Tests;

/// <summary>
/// Test-friendly DbContext that replaces PostgreSQL-specific configurations
/// (PostGIS column types, GIST indexes, JSONB) with InMemory-compatible equivalents.
/// </summary>
public class TestDbContext : GeoChangeDbContext
{
    public TestDbContext(DbContextOptions<GeoChangeDbContext> options)
        : base(options)
    {
    }

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        // Add value converters for Dictionary<string, object> properties
        // that PostgreSQL stores as JSONB but InMemory can't handle natively
        var jsonConverter = new ValueConverter<Dictionary<string, object>?, string?>(
            v => v == null ? null : JsonSerializer.Serialize(v, (JsonSerializerOptions?)null),
            v => v == null ? null : JsonSerializer.Deserialize<Dictionary<string, object>>(v, (JsonSerializerOptions?)null));

        modelBuilder.Entity<Asset>()
            .Property(e => e.Properties)
            .HasConversion(jsonConverter)
            .HasColumnType(null);

        modelBuilder.Entity<ProcessingRun>()
            .Property(e => e.Metadata)
            .HasConversion(jsonConverter)
            .HasColumnType(null);

        modelBuilder.Entity<RiskEvent>()
            .Property(e => e.ScoringFactors)
            .HasConversion(jsonConverter)
            .HasColumnType(null);

        // Remove PostgreSQL-specific column type and index annotations
        foreach (var entityType in modelBuilder.Model.GetEntityTypes())
        {
            foreach (var property in entityType.GetProperties())
            {
                var columnType = property.GetColumnType();
                if (columnType != null && columnType.StartsWith("geometry"))
                {
                    property.SetColumnType(null);
                }
            }

            foreach (var index in entityType.GetIndexes())
            {
                index.SetMethod(null);
            }
        }
    }
}

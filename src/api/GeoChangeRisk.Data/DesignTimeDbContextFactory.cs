using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;
using Microsoft.Extensions.Configuration;

namespace GeoChangeRisk.Data;

/// <summary>
/// Factory for creating DbContext instances at design time (for EF migrations).
/// Reads connection string from appsettings.json / appsettings.Development.json.
/// </summary>
public class DesignTimeDbContextFactory : IDesignTimeDbContextFactory<GeoChangeDbContext>
{
    public GeoChangeDbContext CreateDbContext(string[] args)
    {
        var apiProjectPath = Path.Combine(
            Directory.GetCurrentDirectory(), "..", "GeoChangeRisk.Api");

        var configuration = new ConfigurationBuilder()
            .SetBasePath(apiProjectPath)
            .AddJsonFile("appsettings.json", optional: true)
            .AddJsonFile("appsettings.Development.json", optional: true)
            .Build();

        var connectionString = configuration.GetConnectionString("DefaultConnection");

        if (string.IsNullOrWhiteSpace(connectionString))
            throw new InvalidOperationException(
                "No database connection string found. " +
                "Run the setup script (deployments/local/setup.ps1 or setup.sh) to generate credentials.");

        var optionsBuilder = new DbContextOptionsBuilder<GeoChangeDbContext>();
        optionsBuilder.UseNpgsql(connectionString, options =>
        {
            options.UseNetTopologySuite();
            options.MigrationsAssembly("GeoChangeRisk.Data");
        });

        return new GeoChangeDbContext(optionsBuilder.Options);
    }
}

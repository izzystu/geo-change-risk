using GeoChangeRisk.Api.Jobs;
using GeoChangeRisk.Api.Services;
using GeoChangeRisk.Contracts;
using GeoChangeRisk.Data;
using Hangfire;
using Hangfire.PostgreSql;
using Microsoft.EntityFrameworkCore;
using Minio;
using NetTopologySuite.IO.Converters;
using Npgsql;
using System.Text.Json;
using System.Text.Json.Serialization;

var builder = WebApplication.CreateBuilder(args);

// =============================================================================
// Configure Services
// =============================================================================

// Add controllers with GeoJSON serialization support
builder.Services.AddControllers()
    .AddJsonOptions(options =>
    {
        // Configure GeoJSON serialization for NetTopologySuite geometries
        options.JsonSerializerOptions.Converters.Add(
            new GeoJsonConverterFactory());
        options.JsonSerializerOptions.DefaultIgnoreCondition =
            JsonIgnoreCondition.WhenWritingNull;
        options.JsonSerializerOptions.PropertyNamingPolicy =
            JsonNamingPolicy.CamelCase;
    });

// Configure PostgreSQL with PostGIS
var connectionString = builder.Configuration.GetConnectionString("DefaultConnection");
if (string.IsNullOrWhiteSpace(connectionString))
    throw new InvalidOperationException(
        "Connection string 'DefaultConnection' is not configured. " +
        "Run the setup script to generate appsettings.Development.json.");

// Build data source with dynamic JSON support (required for Dictionary<string, object> columns)
var dataSourceBuilder = new NpgsqlDataSourceBuilder(connectionString);
dataSourceBuilder.UseNetTopologySuite();
dataSourceBuilder.EnableDynamicJson();
var dataSource = dataSourceBuilder.Build();

builder.Services.AddDbContext<GeoChangeDbContext>(options =>
{
    options.UseNpgsql(dataSource, npgsqlOptions =>
    {
        npgsqlOptions.UseNetTopologySuite();
    });
});

// Configure Hangfire with PostgreSQL storage
builder.Services.AddHangfire(configuration => configuration
    .SetDataCompatibilityLevel(CompatibilityLevel.Version_180)
    .UseSimpleAssemblyNameTypeSerializer()
    .UseRecommendedSerializerSettings()
    .UsePostgreSqlStorage(options =>
        options.UseNpgsqlConnection(builder.Configuration.GetConnectionString("DefaultConnection"))));

// Add Hangfire server (processes background jobs)
builder.Services.AddHangfireServer();

// Configure CORS
var corsOrigins = builder.Configuration.GetSection("Cors:AllowedOrigins").Get<string[]>()
    ?? ["http://localhost:5173"];

builder.Services.AddCors(options =>
{
    options.AddDefaultPolicy(policy =>
    {
        policy.WithOrigins(corsOrigins)
            .AllowAnyMethod()
            .AllowAnyHeader();
    });
});

// Configure Swagger/OpenAPI
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen(options =>
{
    options.SwaggerDoc("v1", new()
    {
        Title = "Geo Change Risk API",
        Version = "v1",
        Description = "API for geospatial change detection and risk analysis"
    });
});

// Add health checks
builder.Services.AddHealthChecks()
    .AddDbContextCheck<GeoChangeDbContext>("database");

// Configure MinIO client
var minioEndpoint = builder.Configuration["MinIO:Endpoint"] ?? "localhost:9000";
var minioAccessKey = builder.Configuration["MinIO:AccessKey"];
var minioSecretKey = builder.Configuration["MinIO:SecretKey"];
if (string.IsNullOrWhiteSpace(minioAccessKey) || string.IsNullOrWhiteSpace(minioSecretKey))
    throw new InvalidOperationException(
        "MinIO credentials are not configured (MinIO:AccessKey / MinIO:SecretKey). " +
        "Run the setup script to generate appsettings.Development.json.");
var minioUseSSL = builder.Configuration.GetValue<bool>("MinIO:UseSSL", false);

builder.Services.AddSingleton<IMinioClient>(sp =>
{
    return new MinioClient()
        .WithEndpoint(minioEndpoint)
        .WithCredentials(minioAccessKey, minioSecretKey)
        .WithSSL(minioUseSSL)
        .Build();
});

builder.Services.AddSingleton<IObjectStorageService, ObjectStorageService>();
builder.Services.AddSingleton<IGeometryParsingService, GeometryParsingService>();

// Configure notification service
builder.Services.Configure<NotificationOptions>(
    builder.Configuration.GetSection(NotificationOptions.SectionName));
builder.Services.AddHttpClient();
builder.Services.AddScoped<INotificationService, NotificationService>();

var app = builder.Build();

// =============================================================================
// Configure HTTP Pipeline
// =============================================================================

// Development-only middleware
if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI(options =>
    {
        options.SwaggerEndpoint("/swagger/v1/swagger.json", "Geo Change Risk API v1");
        options.RoutePrefix = "swagger";
    });
}

app.UseCors();

app.UseAuthorization();

app.MapControllers();

// Hangfire dashboard for monitoring jobs
app.UseHangfireDashboard("/hangfire");

// Register recurring check jobs for all scheduled AOIs
try
{
    using var jobScope = app.Services.CreateScope();
    var jobContext = jobScope.ServiceProvider.GetRequiredService<GeoChangeDbContext>();
    var recurringJobs = jobScope.ServiceProvider.GetRequiredService<IRecurringJobManager>();

    var scheduledAois = jobContext.AreasOfInterest
        .Where(a => a.ProcessingEnabled && a.ProcessingSchedule != null)
        .ToList();

    var registeredCount = 0;
    foreach (var aoi in scheduledAois)
    {
        try
        {
            recurringJobs.AddOrUpdate<ScheduledCheckJob>(
                $"scheduled-check-{aoi.AoiId}",
                job => job.ExecuteAsync(aoi.AoiId, CancellationToken.None),
                aoi.ProcessingSchedule!,
                new RecurringJobOptions { TimeZone = TimeZoneInfo.Utc });
            registeredCount++;
        }
        catch (Exception aoiEx)
        {
            app.Logger.LogWarning(aoiEx,
                "Failed to register recurring job for AOI {AoiId} with schedule '{Schedule}'",
                aoi.AoiId, aoi.ProcessingSchedule);
        }
    }

    app.Logger.LogInformation("Registered {Count}/{Total} recurring check jobs", registeredCount, scheduledAois.Count);
}
catch (Exception ex)
{
    app.Logger.LogWarning(ex, "Failed to register recurring jobs on startup");
}

// Health check endpoint
app.MapHealthChecks("/health");

// =============================================================================
// Startup Initialization
// =============================================================================

var logger = app.Services.GetRequiredService<ILogger<Program>>();
logger.LogInformation("Geo Change Risk API starting...");
logger.LogInformation("Environment: {Environment}", app.Environment.EnvironmentName);

// Initialize MinIO buckets on startup
try
{
    var storageService = app.Services.GetRequiredService<IObjectStorageService>();
    var bucketRasters = builder.Configuration["MinIO:BucketRasters"] ?? "geo-rasters";
    var bucketArtifacts = builder.Configuration["MinIO:BucketArtifacts"] ?? "geo-artifacts";
    var bucketImagery = builder.Configuration["MinIO:BucketImagery"] ?? "georisk-imagery";
    var bucketChanges = builder.Configuration["MinIO:BucketChanges"] ?? "georisk-changes";

    await storageService.EnsureBucketExistsAsync(bucketRasters);
    await storageService.EnsureBucketExistsAsync(bucketArtifacts);
    await storageService.EnsureBucketExistsAsync(bucketImagery);
    await storageService.EnsureBucketExistsAsync(bucketChanges);
    logger.LogInformation("MinIO buckets initialized: {Rasters}, {Artifacts}, {Imagery}, {Changes}",
        bucketRasters, bucketArtifacts, bucketImagery, bucketChanges);
}
catch (Exception ex)
{
    logger.LogWarning(ex, "Failed to initialize MinIO buckets. Object storage may not be available.");
}

logger.LogInformation("Swagger UI: http://localhost:{Port}/swagger",
    builder.Configuration.GetValue<int?>("Kestrel:Endpoints:Http:Port") ?? 5074);

app.Run();

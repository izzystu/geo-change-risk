using Amazon.BedrockRuntime;
using Amazon.S3;
using Amazon.Scheduler;
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

// Configure CORS — always allow any origin when deployed to AWS (behind CloudFront)
var isAwsDeployment = builder.Configuration["Storage:Provider"] == "s3";
var corsOrigins = builder.Configuration.GetSection("Cors:AllowedOrigins").Get<string[]>()
    ?? ["http://localhost:5173"];

builder.Services.AddCors(options =>
{
    options.AddDefaultPolicy(policy =>
    {
        if (isAwsDeployment || corsOrigins.Any(o => o == "*"))
        {
            policy.AllowAnyOrigin()
                .AllowAnyMethod()
                .AllowAnyHeader();
        }
        else
        {
            policy.WithOrigins(corsOrigins)
                .AllowAnyMethod()
                .AllowAnyHeader();
        }
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

// Configure object storage (S3 or MinIO)
var storageProvider = builder.Configuration["Storage:Provider"] ?? "minio";

if (storageProvider == "s3")
{
    builder.Services.AddSingleton<IAmazonS3>(new AmazonS3Client());
    builder.Services.AddSingleton<IObjectStorageService, S3ObjectStorageService>();
}
else
{
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
}
builder.Services.AddSingleton<IGeometryParsingService, GeometryParsingService>();

// Configure scheduler (Hangfire or EventBridge)
var schedulerProvider = builder.Configuration["Scheduler:Provider"] ?? "hangfire";

if (schedulerProvider == "eventbridge")
{
    builder.Services.AddSingleton<AmazonSchedulerClient>();
    builder.Services.AddSingleton<ISchedulerService, EventBridgeSchedulerService>();
}
else
{
    builder.Services.AddSingleton<ISchedulerService, HangfireSchedulerService>();
}

// Configure pipeline executor (local subprocess or ECS)
var pipelineMode = builder.Configuration["Pipeline:ExecutionMode"] ?? "local";

if (pipelineMode == "ecs")
{
    builder.Services.AddSingleton<Amazon.ECS.AmazonECSClient>();
    builder.Services.AddSingleton<IPipelineExecutor, EcsPipelineExecutor>();
}
else
{
    builder.Services.AddSingleton<IPipelineExecutor, LocalPipelineExecutor>();
}

// Configure notification service
builder.Services.Configure<NotificationOptions>(
    builder.Configuration.GetSection(NotificationOptions.SectionName));
builder.Services.AddHttpClient();
builder.Services.AddScoped<INotificationService, NotificationService>();

// Configure LLM service (Ollama or Bedrock)
builder.Services.Configure<LlmOptions>(
    builder.Configuration.GetSection(LlmOptions.SectionName));

var llmProvider = builder.Configuration["Llm:Provider"] ?? "ollama";

if (llmProvider == "bedrock")
{
    builder.Services.AddSingleton<AmazonBedrockRuntimeClient>();
    builder.Services.AddScoped<ILlmService, BedrockLlmService>();
}
else
{
    builder.Services.AddScoped<ILlmService, OllamaLlmService>();
}
builder.Services.AddScoped<QueryExecutorService>();

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

// API key authentication middleware
var apiKey = builder.Configuration["Auth:ApiKey"];
if (!string.IsNullOrEmpty(apiKey))
{
    app.Use(async (context, next) =>
    {
        var path = context.Request.Path.Value ?? "";

        // Exempt health check and swagger from auth
        if (path.Equals("/health", StringComparison.OrdinalIgnoreCase) ||
            path.StartsWith("/swagger", StringComparison.OrdinalIgnoreCase) ||
            path.StartsWith("/hangfire", StringComparison.OrdinalIgnoreCase))
        {
            await next();
            return;
        }

        if (!context.Request.Headers.TryGetValue("X-Api-Key", out var providedKey) ||
            providedKey != apiKey)
        {
            context.Response.StatusCode = 401;
            context.Response.ContentType = "application/json";
            await context.Response.WriteAsync("{\"error\":\"Unauthorized\"}");
            return;
        }

        await next();
    });
}

app.UseAuthorization();

app.MapControllers();

// Hangfire dashboard for monitoring jobs
app.UseHangfireDashboard("/hangfire");

// Sync recurring check schedules on startup
try
{
    var schedulerService = app.Services.GetRequiredService<ISchedulerService>();
    await schedulerService.SyncAllSchedulesAsync();
}
catch (Exception ex)
{
    app.Logger.LogWarning(ex, "Failed to sync schedules on startup");
}

// Health check endpoint
app.MapHealthChecks("/health");

// =============================================================================
// Startup Initialization
// =============================================================================

var logger = app.Services.GetRequiredService<ILogger<Program>>();
logger.LogInformation("Geo Change Risk API starting...");
logger.LogInformation("Environment: {Environment}", app.Environment.EnvironmentName);

// Apply pending EF Core migrations on startup
try
{
    using var migrationScope = app.Services.CreateScope();
    var db = migrationScope.ServiceProvider.GetRequiredService<GeoChangeDbContext>();
    await db.Database.MigrateAsync();
    logger.LogInformation("Database migrations applied successfully");
}
catch (Exception ex)
{
    logger.LogWarning(ex, "Failed to apply database migrations on startup");
}

// Initialize storage buckets on startup
try
{
    var storageService = app.Services.GetRequiredService<IObjectStorageService>();
    var bucketRasters = builder.Configuration["Storage:BucketRasters"]
        ?? builder.Configuration["MinIO:BucketRasters"] ?? "geo-rasters";
    var bucketArtifacts = builder.Configuration["Storage:BucketArtifacts"]
        ?? builder.Configuration["MinIO:BucketArtifacts"] ?? "geo-artifacts";
    var bucketImagery = builder.Configuration["Storage:BucketImagery"]
        ?? builder.Configuration["MinIO:BucketImagery"] ?? "georisk-imagery";
    var bucketChanges = builder.Configuration["Storage:BucketChanges"]
        ?? builder.Configuration["MinIO:BucketChanges"] ?? "georisk-changes";

    await storageService.EnsureBucketExistsAsync(bucketRasters);
    await storageService.EnsureBucketExistsAsync(bucketArtifacts);
    await storageService.EnsureBucketExistsAsync(bucketImagery);
    await storageService.EnsureBucketExistsAsync(bucketChanges);
    logger.LogInformation("Storage buckets initialized: {Rasters}, {Artifacts}, {Imagery}, {Changes}",
        bucketRasters, bucketArtifacts, bucketImagery, bucketChanges);
}
catch (Exception ex)
{
    logger.LogWarning(ex, "Failed to initialize storage buckets. Object storage may not be available.");
}

logger.LogInformation("Swagger UI: http://localhost:{Port}/swagger",
    builder.Configuration.GetValue<int?>("Kestrel:Endpoints:Http:Port") ?? 5074);

app.Run();

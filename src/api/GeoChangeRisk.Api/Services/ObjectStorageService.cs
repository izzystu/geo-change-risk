using GeoChangeRisk.Contracts;
using Minio;
using Minio.DataModel.Args;

namespace GeoChangeRisk.Api.Services;

/// <summary>
/// MinIO implementation of object storage service.
/// </summary>
public class ObjectStorageService : IObjectStorageService
{
    private readonly IMinioClient _client;
    private readonly ILogger<ObjectStorageService> _logger;

    public ObjectStorageService(IMinioClient client, ILogger<ObjectStorageService> logger)
    {
        _client = client;
        _logger = logger;
    }

    public async Task UploadAsync(
        string bucket,
        string objectPath,
        Stream stream,
        string contentType = "image/tiff",
        Dictionary<string, string>? metadata = null,
        CancellationToken cancellationToken = default)
    {
        await EnsureBucketExistsAsync(bucket, cancellationToken);

        var putArgs = new PutObjectArgs()
            .WithBucket(bucket)
            .WithObject(objectPath)
            .WithStreamData(stream)
            .WithObjectSize(stream.Length)
            .WithContentType(contentType);

        if (metadata != null)
        {
            putArgs = putArgs.WithHeaders(metadata);
        }

        await _client.PutObjectAsync(putArgs, cancellationToken);
        _logger.LogInformation("Uploaded {ObjectPath} to bucket {Bucket} ({Size} bytes)",
            objectPath, bucket, stream.Length);
    }

    public async Task<Stream> DownloadAsync(
        string bucket,
        string objectPath,
        CancellationToken cancellationToken = default)
    {
        var memoryStream = new MemoryStream();

        var getArgs = new GetObjectArgs()
            .WithBucket(bucket)
            .WithObject(objectPath)
            .WithCallbackStream(stream =>
            {
                stream.CopyTo(memoryStream);
                memoryStream.Position = 0;
            });

        await _client.GetObjectAsync(getArgs, cancellationToken);
        _logger.LogDebug("Downloaded {ObjectPath} from bucket {Bucket}", objectPath, bucket);

        return memoryStream;
    }

    public async Task<string> GetPresignedUrlAsync(
        string bucket,
        string objectPath,
        int expirySeconds = 3600,
        CancellationToken cancellationToken = default)
    {
        var presignedArgs = new PresignedGetObjectArgs()
            .WithBucket(bucket)
            .WithObject(objectPath)
            .WithExpiry(expirySeconds);

        var url = await _client.PresignedGetObjectAsync(presignedArgs);
        _logger.LogDebug("Generated presigned URL for {ObjectPath} (expires in {Seconds}s)",
            objectPath, expirySeconds);

        return url;
    }

    public async Task<bool> ObjectExistsAsync(
        string bucket,
        string objectPath,
        CancellationToken cancellationToken = default)
    {
        try
        {
            var statArgs = new StatObjectArgs()
                .WithBucket(bucket)
                .WithObject(objectPath);

            await _client.StatObjectAsync(statArgs, cancellationToken);
            return true;
        }
        catch (Minio.Exceptions.ObjectNotFoundException)
        {
            return false;
        }
    }

    public async Task<IList<StorageObjectInfo>> ListObjectsAsync(
        string bucket,
        string? prefix = null,
        CancellationToken cancellationToken = default)
    {
        var objects = new List<StorageObjectInfo>();

        var listArgs = new ListObjectsArgs()
            .WithBucket(bucket)
            .WithRecursive(true);

        if (!string.IsNullOrEmpty(prefix))
        {
            listArgs = listArgs.WithPrefix(prefix);
        }

        await foreach (var item in _client.ListObjectsEnumAsync(listArgs, cancellationToken))
        {
            objects.Add(new StorageObjectInfo
            {
                ObjectPath = item.Key,
                Size = (long)item.Size,
                LastModified = item.LastModifiedDateTime ?? DateTime.MinValue,
                ContentType = item.ContentType
            });
        }

        return objects;
    }

    public async Task DeleteAsync(
        string bucket,
        string objectPath,
        CancellationToken cancellationToken = default)
    {
        var removeArgs = new RemoveObjectArgs()
            .WithBucket(bucket)
            .WithObject(objectPath);

        await _client.RemoveObjectAsync(removeArgs, cancellationToken);
        _logger.LogInformation("Deleted {ObjectPath} from bucket {Bucket}", objectPath, bucket);
    }

    public async Task DeleteFolderAsync(
        string bucket,
        string prefix,
        CancellationToken cancellationToken = default)
    {
        var objects = await ListObjectsAsync(bucket, prefix, cancellationToken);

        foreach (var obj in objects)
        {
            await DeleteAsync(bucket, obj.ObjectPath, cancellationToken);
        }

        _logger.LogInformation("Deleted {Count} objects with prefix {Prefix} from bucket {Bucket}",
            objects.Count, prefix, bucket);
    }

    public async Task EnsureBucketExistsAsync(
        string bucket,
        CancellationToken cancellationToken = default)
    {
        var bucketExistsArgs = new BucketExistsArgs().WithBucket(bucket);
        var exists = await _client.BucketExistsAsync(bucketExistsArgs, cancellationToken);

        if (!exists)
        {
            var makeBucketArgs = new MakeBucketArgs().WithBucket(bucket);
            await _client.MakeBucketAsync(makeBucketArgs, cancellationToken);
            _logger.LogInformation("Created bucket {Bucket}", bucket);
        }
    }
}

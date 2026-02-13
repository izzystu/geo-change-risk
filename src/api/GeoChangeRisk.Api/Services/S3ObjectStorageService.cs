using Amazon.S3;
using Amazon.S3.Model;
using GeoChangeRisk.Contracts;

namespace GeoChangeRisk.Api.Services;

/// <summary>
/// AWS S3 implementation of object storage service.
/// Uses IAM role credentials (no access key configuration needed).
/// </summary>
public class S3ObjectStorageService : IObjectStorageService
{
    private readonly IAmazonS3 _client;
    private readonly ILogger<S3ObjectStorageService> _logger;

    public S3ObjectStorageService(IAmazonS3 client, ILogger<S3ObjectStorageService> logger)
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
        var request = new PutObjectRequest
        {
            BucketName = bucket,
            Key = objectPath,
            InputStream = stream,
            ContentType = contentType
        };

        if (metadata != null)
        {
            foreach (var (key, value) in metadata)
            {
                request.Metadata.Add(key, value);
            }
        }

        await _client.PutObjectAsync(request, cancellationToken);
        _logger.LogInformation("Uploaded {ObjectPath} to bucket {Bucket} ({Size} bytes)",
            objectPath, bucket, stream.Length);
    }

    public async Task<Stream> DownloadAsync(
        string bucket,
        string objectPath,
        CancellationToken cancellationToken = default)
    {
        var response = await _client.GetObjectAsync(bucket, objectPath, cancellationToken);

        var memoryStream = new MemoryStream();
        await response.ResponseStream.CopyToAsync(memoryStream, cancellationToken);
        memoryStream.Position = 0;

        _logger.LogDebug("Downloaded {ObjectPath} from bucket {Bucket}", objectPath, bucket);
        return memoryStream;
    }

    public Task<string> GetPresignedUrlAsync(
        string bucket,
        string objectPath,
        int expirySeconds = 3600,
        CancellationToken cancellationToken = default)
    {
        var request = new GetPreSignedUrlRequest
        {
            BucketName = bucket,
            Key = objectPath,
            Expires = DateTime.UtcNow.AddSeconds(expirySeconds)
        };

        var url = _client.GetPreSignedURL(request);
        _logger.LogDebug("Generated presigned URL for {ObjectPath} (expires in {Seconds}s)",
            objectPath, expirySeconds);

        return Task.FromResult(url);
    }

    public async Task<bool> ObjectExistsAsync(
        string bucket,
        string objectPath,
        CancellationToken cancellationToken = default)
    {
        try
        {
            await _client.GetObjectMetadataAsync(bucket, objectPath, cancellationToken);
            return true;
        }
        catch (AmazonS3Exception ex) when (ex.StatusCode == System.Net.HttpStatusCode.NotFound)
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

        var request = new ListObjectsV2Request
        {
            BucketName = bucket,
            Prefix = prefix
        };

        ListObjectsV2Response response;
        do
        {
            response = await _client.ListObjectsV2Async(request, cancellationToken);

            foreach (var obj in response.S3Objects)
            {
                objects.Add(new StorageObjectInfo
                {
                    ObjectPath = obj.Key,
                    Size = obj.Size,
                    LastModified = obj.LastModified
                });
            }

            request.ContinuationToken = response.NextContinuationToken;
        } while (response.IsTruncated);

        return objects;
    }

    public async Task DeleteAsync(
        string bucket,
        string objectPath,
        CancellationToken cancellationToken = default)
    {
        await _client.DeleteObjectAsync(bucket, objectPath, cancellationToken);
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

    public Task EnsureBucketExistsAsync(
        string bucket,
        CancellationToken cancellationToken = default)
    {
        // No-op on AWS — buckets are created by Terraform
        _logger.LogDebug("EnsureBucketExists is a no-op on S3 (bucket {Bucket} managed by Terraform)", bucket);
        return Task.CompletedTask;
    }
}

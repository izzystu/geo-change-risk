namespace GeoChangeRisk.Contracts;

/// <summary>
/// Interface for S3-compatible object storage operations.
/// </summary>
public interface IObjectStorageService
{
    /// <summary>
    /// Uploads a COG (Cloud Optimized GeoTIFF) to storage.
    /// </summary>
    /// <param name="bucket">Target bucket name.</param>
    /// <param name="objectPath">Object path within bucket (e.g., "paradise-ca/scene-123/ndvi.tif").</param>
    /// <param name="stream">File content stream.</param>
    /// <param name="contentType">MIME type (defaults to image/tiff).</param>
    /// <param name="metadata">Optional metadata dictionary.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    Task UploadAsync(
        string bucket,
        string objectPath,
        Stream stream,
        string contentType = "image/tiff",
        Dictionary<string, string>? metadata = null,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Downloads a file from storage.
    /// </summary>
    /// <param name="bucket">Source bucket name.</param>
    /// <param name="objectPath">Object path within bucket.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Stream containing file content.</returns>
    Task<Stream> DownloadAsync(
        string bucket,
        string objectPath,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Gets a presigned URL for direct client access.
    /// </summary>
    /// <param name="bucket">Bucket name.</param>
    /// <param name="objectPath">Object path within bucket.</param>
    /// <param name="expirySeconds">URL expiration time in seconds (default 3600 = 1 hour).</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>Presigned URL string.</returns>
    Task<string> GetPresignedUrlAsync(
        string bucket,
        string objectPath,
        int expirySeconds = 3600,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Checks if an object exists in storage.
    /// </summary>
    /// <param name="bucket">Bucket name.</param>
    /// <param name="objectPath">Object path within bucket.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>True if object exists, false otherwise.</returns>
    Task<bool> ObjectExistsAsync(
        string bucket,
        string objectPath,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Lists objects in a bucket with optional prefix filter.
    /// </summary>
    /// <param name="bucket">Bucket name.</param>
    /// <param name="prefix">Optional prefix to filter objects.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    /// <returns>List of object paths.</returns>
    Task<IList<StorageObjectInfo>> ListObjectsAsync(
        string bucket,
        string? prefix = null,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Deletes an object from storage.
    /// </summary>
    /// <param name="bucket">Bucket name.</param>
    /// <param name="objectPath">Object path within bucket.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    Task DeleteAsync(
        string bucket,
        string objectPath,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Deletes all objects under a folder prefix.
    /// </summary>
    /// <param name="bucket">Bucket name.</param>
    /// <param name="prefix">Folder prefix to delete (e.g., "aoiId/sceneId/").</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    Task DeleteFolderAsync(
        string bucket,
        string prefix,
        CancellationToken cancellationToken = default);

    /// <summary>
    /// Ensures a bucket exists, creating it if necessary.
    /// </summary>
    /// <param name="bucket">Bucket name to ensure exists.</param>
    /// <param name="cancellationToken">Cancellation token.</param>
    Task EnsureBucketExistsAsync(
        string bucket,
        CancellationToken cancellationToken = default);
}

/// <summary>
/// Information about a storage object.
/// </summary>
public class StorageObjectInfo
{
    /// <summary>Full object path/key.</summary>
    public required string ObjectPath { get; set; }

    /// <summary>Object size in bytes.</summary>
    public long Size { get; set; }

    /// <summary>Last modified timestamp.</summary>
    public DateTime LastModified { get; set; }

    /// <summary>Content type (MIME type).</summary>
    public string? ContentType { get; set; }
}

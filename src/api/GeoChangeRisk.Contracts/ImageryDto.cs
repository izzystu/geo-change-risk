using System.Text.Json.Serialization;

namespace GeoChangeRisk.Contracts;

public class ImagerySceneDto
{
    public required string SceneId { get; set; }
    public required string AoiId { get; set; }
    public required List<ImageryFileDto> Files { get; set; }
    public DateTime LastModified { get; set; }
}

public class ImageryFileDto
{
    public required string FileName { get; set; }
    public required string ObjectPath { get; set; }
    public long Size { get; set; }
    public DateTime LastModified { get; set; }
}

public class ImagerySceneDetailDto
{
    public required string SceneId { get; set; }
    public required string AoiId { get; set; }
    public required double[] Bounds { get; set; }
    public required List<ImageryFileWithUrlDto> Files { get; set; }
    /// <summary>
    /// Presigned URL for web display (PNG preferred over TIF).
    /// </summary>
    public string? DisplayUrl { get; set; }
    public DateTime LastModified { get; set; }
}

public class ImageryFileWithUrlDto
{
    public required string FileName { get; set; }
    public required string ObjectPath { get; set; }
    public long Size { get; set; }
    public DateTime LastModified { get; set; }
    public required string PresignedUrl { get; set; }
}

public class ImageryUploadResultDto
{
    public required string ObjectPath { get; set; }
    public long Size { get; set; }
    public required string PresignedUrl { get; set; }
    public required string Message { get; set; }
}

/// <summary>
/// Metadata from bounds.json sidecar file for accurate imagery georeferencing.
/// </summary>
public class BoundsMetadata
{
    [JsonPropertyName("bounds")]
    public double[]? Bounds { get; set; }

    [JsonPropertyName("crs")]
    public string? Crs { get; set; }

    [JsonPropertyName("scene_id")]
    public string? SceneId { get; set; }
}

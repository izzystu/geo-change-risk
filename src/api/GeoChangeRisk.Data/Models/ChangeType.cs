namespace GeoChangeRisk.Data.Models;

/// <summary>
/// Type of land-surface change detected in satellite imagery.
/// </summary>
public enum ChangeType
{
    /// <summary>Change type could not be determined with confidence</summary>
    Unknown = 0,

    /// <summary>Significant vegetation loss detected</summary>
    VegetationLoss = 1,

    /// <summary>Vegetation growth or recovery detected</summary>
    VegetationGain = 2,

    /// <summary>Wildfire burn scar (ML-classified)</summary>
    FireBurnScar = 3,

    /// <summary>Drought stress in vegetation (ML-classified)</summary>
    DroughtStress = 4,

    /// <summary>Agricultural activity change (ML-classified)</summary>
    AgriculturalChange = 5,

    /// <summary>Landslide or debris flow (ML-classified)</summary>
    LandslideDebris = 6,
}

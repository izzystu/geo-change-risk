namespace GeoChangeRisk.Data.Models;

/// <summary>
/// Types of infrastructure assets that can be monitored.
/// </summary>
public enum AssetType
{
    /// <summary>Electric transmission lines (from CEC data)</summary>
    TransmissionLine = 0,

    /// <summary>Electric substations (from CEC data)</summary>
    Substation = 1,

    /// <summary>Gas transmission pipelines (from PHMSA data)</summary>
    GasPipeline = 2,

    /// <summary>Buildings and structures (from OSM data)</summary>
    Building = 3,

    /// <summary>Roads and highways (from OSM data)</summary>
    Road = 4,

    /// <summary>Fire stations (from HIFLD data)</summary>
    FireStation = 5,

    /// <summary>Hospitals and medical facilities (from HIFLD data)</summary>
    Hospital = 6,

    /// <summary>Schools and universities (from HIFLD data)</summary>
    School = 7,

    /// <summary>Water infrastructure - canals, aqueducts (from NHD/CNRA data)</summary>
    WaterInfrastructure = 8,

    /// <summary>Other/unclassified asset type</summary>
    Other = 99
}

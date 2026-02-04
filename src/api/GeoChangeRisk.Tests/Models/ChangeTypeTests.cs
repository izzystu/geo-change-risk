using GeoChangeRisk.Data.Models;
using Xunit;

namespace GeoChangeRisk.Tests.Models;

public class ChangeTypeTests
{
    [Fact]
    public void ChangeType_values_are_sequential_0_through_6()
    {
        var values = Enum.GetValues<ChangeType>()
            .Select(v => (int)v)
            .OrderBy(v => v)
            .ToList();

        Assert.Equal(Enumerable.Range(0, 7).ToList(), values);
    }

    [Theory]
    [InlineData(ChangeType.Unknown, 0)]
    [InlineData(ChangeType.VegetationLoss, 1)]
    [InlineData(ChangeType.VegetationGain, 2)]
    [InlineData(ChangeType.FireBurnScar, 3)]
    [InlineData(ChangeType.DroughtStress, 4)]
    [InlineData(ChangeType.AgriculturalChange, 5)]
    [InlineData(ChangeType.LandslideDebris, 6)]
    public void ChangeType_has_expected_integer_value(ChangeType type, int expected)
    {
        Assert.Equal(expected, (int)type);
    }
}

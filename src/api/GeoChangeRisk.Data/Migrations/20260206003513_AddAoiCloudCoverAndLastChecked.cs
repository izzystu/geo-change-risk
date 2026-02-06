using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace GeoChangeRisk.Data.Migrations
{
    /// <inheritdoc />
    public partial class AddAoiCloudCoverAndLastChecked : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<DateTime>(
                name: "LastCheckedAt",
                table: "AreasOfInterest",
                type: "timestamp with time zone",
                nullable: true);

            migrationBuilder.AddColumn<double>(
                name: "MaxCloudCover",
                table: "AreasOfInterest",
                type: "double precision",
                nullable: false,
                defaultValue: 20.0);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "LastCheckedAt",
                table: "AreasOfInterest");

            migrationBuilder.DropColumn(
                name: "MaxCloudCover",
                table: "AreasOfInterest");
        }
    }
}

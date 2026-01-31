using System;
using System.Collections.Generic;
using Microsoft.EntityFrameworkCore.Migrations;
using NetTopologySuite.Geometries;

#nullable disable

namespace GeoChangeRisk.Data.Migrations
{
    /// <inheritdoc />
    public partial class InitialCreate : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AlterDatabase()
                .Annotation("Npgsql:PostgresExtension:postgis", ",,");

            migrationBuilder.CreateTable(
                name: "AreasOfInterest",
                columns: table => new
                {
                    AoiId = table.Column<string>(type: "character varying(100)", maxLength: 100, nullable: false),
                    Name = table.Column<string>(type: "character varying(200)", maxLength: 200, nullable: false),
                    Description = table.Column<string>(type: "character varying(2000)", maxLength: 2000, nullable: true),
                    BoundingBox = table.Column<Polygon>(type: "geometry(Polygon, 4326)", nullable: false),
                    CenterPoint = table.Column<Point>(type: "geometry(Point, 4326)", nullable: false),
                    CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false, defaultValueSql: "CURRENT_TIMESTAMP"),
                    UpdatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_AreasOfInterest", x => x.AoiId);
                });

            migrationBuilder.CreateTable(
                name: "Assets",
                columns: table => new
                {
                    AssetId = table.Column<string>(type: "character varying(100)", maxLength: 100, nullable: false),
                    AoiId = table.Column<string>(type: "character varying(100)", maxLength: 100, nullable: false),
                    Name = table.Column<string>(type: "character varying(500)", maxLength: 500, nullable: false),
                    AssetType = table.Column<int>(type: "integer", nullable: false),
                    Geometry = table.Column<Geometry>(type: "geometry(Geometry, 4326)", nullable: false),
                    Criticality = table.Column<int>(type: "integer", nullable: false),
                    Properties = table.Column<Dictionary<string, object>>(type: "jsonb", nullable: true),
                    SourceDataset = table.Column<string>(type: "character varying(100)", maxLength: 100, nullable: true),
                    SourceFeatureId = table.Column<string>(type: "character varying(200)", maxLength: 200, nullable: true),
                    CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false, defaultValueSql: "CURRENT_TIMESTAMP"),
                    UpdatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Assets", x => x.AssetId);
                    table.ForeignKey(
                        name: "FK_Assets_AreasOfInterest_AoiId",
                        column: x => x.AoiId,
                        principalTable: "AreasOfInterest",
                        principalColumn: "AoiId",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_AreasOfInterest_BoundingBox",
                table: "AreasOfInterest",
                column: "BoundingBox")
                .Annotation("Npgsql:IndexMethod", "gist");

            migrationBuilder.CreateIndex(
                name: "IX_Assets_AoiId",
                table: "Assets",
                column: "AoiId");

            migrationBuilder.CreateIndex(
                name: "IX_Assets_AoiId_AssetType",
                table: "Assets",
                columns: new[] { "AoiId", "AssetType" });

            migrationBuilder.CreateIndex(
                name: "IX_Assets_AssetType",
                table: "Assets",
                column: "AssetType");

            migrationBuilder.CreateIndex(
                name: "IX_Assets_Geometry",
                table: "Assets",
                column: "Geometry")
                .Annotation("Npgsql:IndexMethod", "gist");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "Assets");

            migrationBuilder.DropTable(
                name: "AreasOfInterest");
        }
    }
}

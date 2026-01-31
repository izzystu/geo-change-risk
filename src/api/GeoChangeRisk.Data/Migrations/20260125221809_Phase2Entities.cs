using System;
using System.Collections.Generic;
using Microsoft.EntityFrameworkCore.Migrations;
using NetTopologySuite.Geometries;

#nullable disable

namespace GeoChangeRisk.Data.Migrations
{
    /// <inheritdoc />
    public partial class Phase2Entities : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<int>(
                name: "DefaultLookbackDays",
                table: "AreasOfInterest",
                type: "integer",
                nullable: false,
                defaultValue: 0);

            migrationBuilder.AddColumn<DateTime>(
                name: "LastProcessedAt",
                table: "AreasOfInterest",
                type: "timestamp with time zone",
                nullable: true);

            migrationBuilder.AddColumn<bool>(
                name: "ProcessingEnabled",
                table: "AreasOfInterest",
                type: "boolean",
                nullable: false,
                defaultValue: false);

            migrationBuilder.AddColumn<string>(
                name: "ProcessingSchedule",
                table: "AreasOfInterest",
                type: "character varying(50)",
                maxLength: 50,
                nullable: true);

            migrationBuilder.CreateTable(
                name: "ProcessingRuns",
                columns: table => new
                {
                    RunId = table.Column<Guid>(type: "uuid", nullable: false, defaultValueSql: "gen_random_uuid()"),
                    AoiId = table.Column<string>(type: "character varying(100)", maxLength: 100, nullable: false),
                    Status = table.Column<int>(type: "integer", nullable: false),
                    BeforeDate = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    AfterDate = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    BeforeSceneId = table.Column<string>(type: "character varying(500)", maxLength: 500, nullable: true),
                    AfterSceneId = table.Column<string>(type: "character varying(500)", maxLength: 500, nullable: true),
                    StartedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    CompletedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    ErrorMessage = table.Column<string>(type: "character varying(4000)", maxLength: 4000, nullable: true),
                    Metadata = table.Column<Dictionary<string, object>>(type: "jsonb", nullable: true),
                    CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false, defaultValueSql: "CURRENT_TIMESTAMP")
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ProcessingRuns", x => x.RunId);
                    table.ForeignKey(
                        name: "FK_ProcessingRuns_AreasOfInterest_AoiId",
                        column: x => x.AoiId,
                        principalTable: "AreasOfInterest",
                        principalColumn: "AoiId",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "ChangePolygons",
                columns: table => new
                {
                    ChangePolygonId = table.Column<Guid>(type: "uuid", nullable: false, defaultValueSql: "gen_random_uuid()"),
                    RunId = table.Column<Guid>(type: "uuid", nullable: false),
                    Geometry = table.Column<Polygon>(type: "geometry(Polygon, 4326)", nullable: false),
                    AreaSqMeters = table.Column<double>(type: "double precision", nullable: false),
                    NdviDropMean = table.Column<double>(type: "double precision", nullable: false),
                    NdviDropMax = table.Column<double>(type: "double precision", nullable: false),
                    ChangeType = table.Column<int>(type: "integer", nullable: false),
                    SlopeDegreeMean = table.Column<double>(type: "double precision", nullable: true),
                    DetectedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false, defaultValueSql: "CURRENT_TIMESTAMP"),
                    MlConfidence = table.Column<double>(type: "double precision", nullable: true),
                    MlModelVersion = table.Column<string>(type: "character varying(100)", maxLength: 100, nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ChangePolygons", x => x.ChangePolygonId);
                    table.ForeignKey(
                        name: "FK_ChangePolygons_ProcessingRuns_RunId",
                        column: x => x.RunId,
                        principalTable: "ProcessingRuns",
                        principalColumn: "RunId",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "RiskEvents",
                columns: table => new
                {
                    RiskEventId = table.Column<Guid>(type: "uuid", nullable: false, defaultValueSql: "gen_random_uuid()"),
                    ChangePolygonId = table.Column<Guid>(type: "uuid", nullable: false),
                    AssetId = table.Column<string>(type: "character varying(100)", maxLength: 100, nullable: false),
                    DistanceMeters = table.Column<double>(type: "double precision", nullable: false),
                    RiskScore = table.Column<int>(type: "integer", nullable: false),
                    RiskLevel = table.Column<int>(type: "integer", nullable: false),
                    ScoringFactors = table.Column<Dictionary<string, object>>(type: "jsonb", nullable: true),
                    CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false, defaultValueSql: "CURRENT_TIMESTAMP"),
                    NotificationSentAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    AcknowledgedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true),
                    AcknowledgedBy = table.Column<string>(type: "character varying(200)", maxLength: 200, nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_RiskEvents", x => x.RiskEventId);
                    table.ForeignKey(
                        name: "FK_RiskEvents_Assets_AssetId",
                        column: x => x.AssetId,
                        principalTable: "Assets",
                        principalColumn: "AssetId",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_RiskEvents_ChangePolygons_ChangePolygonId",
                        column: x => x.ChangePolygonId,
                        principalTable: "ChangePolygons",
                        principalColumn: "ChangePolygonId",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_ChangePolygons_ChangeType",
                table: "ChangePolygons",
                column: "ChangeType");

            migrationBuilder.CreateIndex(
                name: "IX_ChangePolygons_Geometry",
                table: "ChangePolygons",
                column: "Geometry")
                .Annotation("Npgsql:IndexMethod", "gist");

            migrationBuilder.CreateIndex(
                name: "IX_ChangePolygons_RunId",
                table: "ChangePolygons",
                column: "RunId");

            migrationBuilder.CreateIndex(
                name: "IX_ProcessingRuns_AoiId",
                table: "ProcessingRuns",
                column: "AoiId");

            migrationBuilder.CreateIndex(
                name: "IX_ProcessingRuns_AoiId_Status",
                table: "ProcessingRuns",
                columns: new[] { "AoiId", "Status" });

            migrationBuilder.CreateIndex(
                name: "IX_ProcessingRuns_Status",
                table: "ProcessingRuns",
                column: "Status");

            migrationBuilder.CreateIndex(
                name: "IX_RiskEvents_AssetId",
                table: "RiskEvents",
                column: "AssetId");

            migrationBuilder.CreateIndex(
                name: "IX_RiskEvents_AssetId_RiskLevel",
                table: "RiskEvents",
                columns: new[] { "AssetId", "RiskLevel" });

            migrationBuilder.CreateIndex(
                name: "IX_RiskEvents_ChangePolygonId",
                table: "RiskEvents",
                column: "ChangePolygonId");

            migrationBuilder.CreateIndex(
                name: "IX_RiskEvents_RiskLevel",
                table: "RiskEvents",
                column: "RiskLevel");

            migrationBuilder.CreateIndex(
                name: "IX_RiskEvents_RiskScore",
                table: "RiskEvents",
                column: "RiskScore");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "RiskEvents");

            migrationBuilder.DropTable(
                name: "ChangePolygons");

            migrationBuilder.DropTable(
                name: "ProcessingRuns");

            migrationBuilder.DropColumn(
                name: "DefaultLookbackDays",
                table: "AreasOfInterest");

            migrationBuilder.DropColumn(
                name: "LastProcessedAt",
                table: "AreasOfInterest");

            migrationBuilder.DropColumn(
                name: "ProcessingEnabled",
                table: "AreasOfInterest");

            migrationBuilder.DropColumn(
                name: "ProcessingSchedule",
                table: "AreasOfInterest");
        }
    }
}

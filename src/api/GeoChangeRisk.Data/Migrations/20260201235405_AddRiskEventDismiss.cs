using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace GeoChangeRisk.Data.Migrations
{
    /// <inheritdoc />
    public partial class AddRiskEventDismiss : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<DateTime>(
                name: "DismissedAt",
                table: "RiskEvents",
                type: "timestamp with time zone",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "DismissedBy",
                table: "RiskEvents",
                type: "text",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "DismissedAt",
                table: "RiskEvents");

            migrationBuilder.DropColumn(
                name: "DismissedBy",
                table: "RiskEvents");
        }
    }
}

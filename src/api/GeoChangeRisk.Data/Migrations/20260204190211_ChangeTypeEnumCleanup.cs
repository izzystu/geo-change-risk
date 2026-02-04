using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace GeoChangeRisk.Data.Migrations
{
    /// <inheritdoc />
    public partial class ChangeTypeEnumCleanup : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            // Remap ChangeType integer values from old scheme to new sequential scheme.
            // Must handle both the buggy Python values (5,7,8) and the C# enum values (10-14).

            // Phase 1: Move old values to temporary high values to avoid collisions
            migrationBuilder.Sql(@"
                UPDATE ""ChangePolygons"" SET ""ChangeType"" = 100 WHERE ""ChangeType"" = 5;
                UPDATE ""ChangePolygons"" SET ""ChangeType"" = 101 WHERE ""ChangeType"" = 10;
                UPDATE ""ChangePolygons"" SET ""ChangeType"" = 102 WHERE ""ChangeType"" = 7;
                UPDATE ""ChangePolygons"" SET ""ChangeType"" = 103 WHERE ""ChangeType"" = 12;
                UPDATE ""ChangePolygons"" SET ""ChangeType"" = 104 WHERE ""ChangeType"" = 8;
                UPDATE ""ChangePolygons"" SET ""ChangeType"" = 105 WHERE ""ChangeType"" = 14;
                UPDATE ""ChangePolygons"" SET ""ChangeType"" = 106 WHERE ""ChangeType"" = 6;
                UPDATE ""ChangePolygons"" SET ""ChangeType"" = 107 WHERE ""ChangeType"" = 11;
            ");

            // Phase 2: Map temp values to new sequential values
            migrationBuilder.Sql(@"
                UPDATE ""ChangePolygons"" SET ""ChangeType"" = 3 WHERE ""ChangeType"" IN (100, 101);
                UPDATE ""ChangePolygons"" SET ""ChangeType"" = 4 WHERE ""ChangeType"" IN (102, 103);
                UPDATE ""ChangePolygons"" SET ""ChangeType"" = 5 WHERE ""ChangeType"" IN (104, 105);
                UPDATE ""ChangePolygons"" SET ""ChangeType"" = 6 WHERE ""ChangeType"" IN (106, 107);
            ");

            // Phase 3: Set any remaining unmapped values to Unknown (0)
            migrationBuilder.Sql(@"
                UPDATE ""ChangePolygons"" SET ""ChangeType"" = 0
                WHERE ""ChangeType"" NOT IN (0, 1, 2, 3, 4, 5, 6);
            ");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            // Reverse mapping: new sequential values back to old C# enum values
            migrationBuilder.Sql(@"
                UPDATE ""ChangePolygons"" SET ""ChangeType"" = 100 WHERE ""ChangeType"" = 3;
                UPDATE ""ChangePolygons"" SET ""ChangeType"" = 101 WHERE ""ChangeType"" = 4;
                UPDATE ""ChangePolygons"" SET ""ChangeType"" = 102 WHERE ""ChangeType"" = 5;
                UPDATE ""ChangePolygons"" SET ""ChangeType"" = 103 WHERE ""ChangeType"" = 6;
            ");

            migrationBuilder.Sql(@"
                UPDATE ""ChangePolygons"" SET ""ChangeType"" = 10 WHERE ""ChangeType"" = 100;
                UPDATE ""ChangePolygons"" SET ""ChangeType"" = 12 WHERE ""ChangeType"" = 101;
                UPDATE ""ChangePolygons"" SET ""ChangeType"" = 14 WHERE ""ChangeType"" = 102;
                UPDATE ""ChangePolygons"" SET ""ChangeType"" = 11 WHERE ""ChangeType"" = 103;
            ");
        }
    }
}

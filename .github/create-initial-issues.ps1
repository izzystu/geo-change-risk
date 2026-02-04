# Create Initial GitHub Issues from Code Review
# Run once after pushing to GitHub: pwsh .github/create-initial-issues.ps1
# Requires: gh CLI authenticated (gh auth login)

Write-Host "Creating issues from code review findings..." -ForegroundColor Cyan
Write-Host ""

# --- Security Issues ---

gh issue create `
    --title "Sanitize user-supplied filenames in ImageryController.UploadCog" `
    --label "security,component:api,priority:high" `
    --body @"
## Problem
``ImageryController.cs:209`` passes user-supplied filename directly to MinIO without sanitization. A filename containing ``../`` could cause path traversal.

## Proposed Fix
Apply ``Path.GetFileName()`` to strip directory components before passing to storage.

## Acceptance Criteria
- [ ] Filename is sanitized before use in object key
- [ ] Unit test covers malicious filename input
"@

gh issue create `
    --title "Sanitize or remove raw HTML rendering in ConfirmDialog" `
    --label "security,component:web-ui,priority:medium" `
    --body @"
## Problem
``ConfirmDialog.svelte:16`` uses ``{@html message}`` which renders raw HTML. Currently only used with hardcoded strings, but if message ever comes from user input or API data, this creates an XSS vulnerability.

## Proposed Fix
Replace ``{@html message}`` with ``{message}`` for text-only rendering, or use a sanitization library like DOMPurify if rich text is needed.

## Acceptance Criteria
- [ ] ConfirmDialog no longer renders unsanitized HTML
"@

gh issue create `
    --title "Add MinIO credential validation on config initialization" `
    --label "security,component:pipeline,priority:medium" `
    --body @"
## Problem
``config.py:26-27`` defaults MinIO ``access_key`` and ``secret_key`` to empty strings. If env vars are not set, the client silently connects without credentials.

## Proposed Fix
Add ``__post_init__`` validation to the ``MinioConfig`` dataclass that raises ``ValueError`` when credentials are missing.

## Acceptance Criteria
- [ ] App fails fast with clear error message when MinIO credentials are not configured
"@

# --- Code Quality Issues ---

gh issue create `
    --title "Replace fragile relative path in RasterProcessingJob" `
    --label "tech-debt,component:api,priority:high" `
    --body @"
## Problem
``RasterProcessingJob.cs:50`` calculates the pipeline directory using ``../../../../../pipeline`` relative to the assembly base directory. This breaks if the build output structure changes (Debug vs Release, publish, etc.).

## Proposed Fix
Read the pipeline directory from ``IConfiguration`` (already in ``appsettings.json`` as ``Python:PipelineDir``). The setup scripts already generate the correct values.

## Acceptance Criteria
- [ ] Pipeline path is read from configuration, not calculated from assembly location
- [ ] Works in both Debug and Release configurations
"@

gh issue create `
    --title "Fix fragile ID generation via string truncation in AssetsController" `
    --label "bug,component:api,priority:medium" `
    --body @"
## Problem
``AssetsController.cs:107`` generates asset external IDs by concatenating the AOI ID with a GUID and truncating to 36 characters: ``\$"{request.AoiId}-{Guid.NewGuid():N}"[..36]``.

If AoiId is long, the GUID portion gets truncated, increasing collision risk.

## Proposed Fix
Use a deterministic approach: hash the combination or use the full GUID and validate against the 100-char DB limit.

## Acceptance Criteria
- [ ] Generated IDs are unique regardless of AOI ID length
- [ ] IDs respect the database column limit
"@

gh issue create `
    --title "Add input validation to API controllers" `
    --label "tech-debt,component:api,priority:medium" `
    --body @"
## Problem
Multiple controllers accept string inputs without validating lengths. The database has max-length constraints, but validation should happen at the API layer to return proper 400 responses instead of 500s.

## Proposed Fix
Add FluentValidation or DataAnnotations to request DTOs. Validate string lengths, required fields, and enum ranges.

## Acceptance Criteria
- [ ] All create/update endpoints validate input before processing
- [ ] Invalid input returns 400 with descriptive error messages
"@

gh issue create `
    --title "Narrow exception handling in Python CLI" `
    --label "tech-debt,component:pipeline,priority:low" `
    --body @"
## Problem
``cli.py:363-371`` uses broad ``except Exception`` with silent ``pass`` in cleanup blocks. This hides real errors.

## Proposed Fix
- Catch specific exception types
- Log cleanup failures at warning level instead of silently swallowing them

## Acceptance Criteria
- [ ] No bare ``except Exception: pass`` blocks remain
- [ ] Cleanup failures are logged
"@

gh issue create `
    --title "Make Python config module thread-safe" `
    --label "tech-debt,component:pipeline,priority:low" `
    --body @"
## Problem
``config.py:168-186`` uses a global mutable ``_config`` variable without synchronization. Concurrent access from multiple threads could cause race conditions.

## Proposed Fix
Add ``threading.Lock`` around config access, or switch to dependency injection.

## Acceptance Criteria
- [ ] Concurrent calls to ``get_config()`` / ``reload_config()`` are safe
"@

gh issue create `
    --title "Add date range validation in CLI" `
    --label "tech-debt,component:pipeline,priority:low" `
    --body @"
## Problem
``cli.py:67`` parses date ranges via ``split("/")`` with no format validation. Invalid dates propagate downstream.

## Proposed Fix
Validate with ``datetime.strptime()`` or ``dateutil.parser`` and return a clear error to the user.

## Acceptance Criteria
- [ ] Invalid date formats produce a helpful error message
- [ ] Start date must be before end date
"@

gh issue create `
    --title "Refactor MapView into smaller components" `
    --label "tech-debt,component:web-ui,priority:medium" `
    --body @"
## Problem
``MapView.svelte`` is 561 lines handling 7+ distinct concerns: map init, asset layers, imagery layers, change polygons, risk event navigation, and reactive state management.

## Proposed Fix
Extract into focused composable components: ``AssetLayer.svelte``, ``ImageryLayer.svelte``, ``ChangePolygonLayer.svelte``, etc.

## Acceptance Criteria
- [ ] MapView delegates rendering concerns to child components
- [ ] No component exceeds ~200 lines
"@

gh issue create `
    --title "Fix Blob URL memory leak in MapView" `
    --label "bug,component:web-ui,priority:medium" `
    --body @"
## Problem
``MapView.svelte:177,405`` creates Blob URLs via ``URL.createObjectURL()`` but never revokes them. Over time this leaks memory.

## Proposed Fix
Call ``URL.revokeObjectURL()`` when layers are replaced or the component is destroyed.

## Acceptance Criteria
- [ ] All created Blob URLs are revoked when no longer needed
"@

# --- Test Coverage ---

gh issue create `
    --title "Add Python tests for cli, db client, change detection, storage, and config" `
    --label "testing,component:pipeline,priority:high" `
    --body @"
## Problem
Test coverage gaps exist for critical modules:
- ``cli.py`` (main entry point, no tests)
- ``db/client.py`` (API integration, no tests)
- ``raster/change.py`` (had the NDVI min/max bug, no tests to catch it)
- ``storage/minio.py`` (no tests)
- ``config.py`` (no tests)

## Acceptance Criteria
- [ ] Unit tests for CLI commands (with mocked dependencies)
- [ ] Unit tests for DB client (with mocked HTTP)
- [ ] Unit tests for change detection (would have caught the min/max swap)
- [ ] Unit tests for MinIO storage (with mocked boto3)
- [ ] Unit tests for config loading and validation
- [ ] Coverage report configured via pytest-cov
"@

gh issue create `
    --title "Add .NET tests for Processing, RiskEvents, Imagery controllers" `
    --label "testing,component:api,priority:high" `
    --body @"
## Problem
Only AreasOfInterest, Assets, and GeometryParsing have unit tests. Missing coverage for:
- ``ProcessingController``
- ``RiskEventsController``
- ``ImageryController``
- ``RasterProcessingJob`` (background job)

## Acceptance Criteria
- [ ] Unit tests for each missing controller
- [ ] Tests cover both success and failure paths
- [ ] Background job tested with mocked dependencies
"@

gh issue create `
    --title "Set up test infrastructure for web UI" `
    --label "testing,component:web-ui,priority:medium" `
    --body @"
## Problem
The web UI has no test runner, no unit tests, and no linting.

## Proposed Approach
- Add Vitest for component/store unit testing
- Add ESLint + Prettier for code quality
- Add tests for Svelte stores (most testable layer)

## Acceptance Criteria
- [ ] Vitest configured and running
- [ ] ESLint + Prettier configured
- [ ] At least store modules have unit tests
"@

# --- Minor / Nice-to-Have ---

gh issue create `
    --title "Add software license to the repository" `
    --label "component:docs,priority:low" `
    --body @"
## Problem
``README.md:207`` has a placeholder: '[License information to be added]'.

## Action
Choose and add a LICENSE file (MIT, Apache 2.0, etc.) and update the README reference.
"@

gh issue create `
    --title "Add missing Pillow dependency to pipeline requirements.txt" `
    --label "bug,component:pipeline,priority:low" `
    --body @"
## Problem
``download.py`` imports Pillow (``from PIL import Image``) but ``requirements.txt`` does not list it. It is listed in ``pyproject.toml`` but the standalone requirements file is incomplete.

## Fix
Add ``Pillow>=10.0.0`` to ``src/pipeline/requirements.txt``.
"@

gh issue create `
    --title "Add accessibility (a11y) improvements to web UI" `
    --label "enhancement,component:web-ui,priority:low" `
    --body @"
## Problem
The web UI has minimal accessibility support:
- No ARIA labels on complex components (MapView)
- No keyboard navigation for panels
- Status icons use Unicode characters without alt text
- Color-only risk badges need contrast improvements

## Acceptance Criteria
- [ ] ARIA labels on interactive elements
- [ ] Keyboard navigation for panel controls
- [ ] Screen reader support for status changes
"@

Write-Host ""
Write-Host "Done! All issues created." -ForegroundColor Green
Write-Host "Run 'gh issue list' to see them." -ForegroundColor Gray

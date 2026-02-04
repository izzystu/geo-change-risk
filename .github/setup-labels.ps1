# GitHub Label Setup Script
# Run once after creating the repo: pwsh .github/setup-labels.ps1
# Requires: gh CLI authenticated (gh auth login)

param(
    [string]$Repo = ""
)

if (-not $Repo) {
    $Repo = gh repo view --json nameWithOwner -q '.nameWithOwner' 2>$null
    if (-not $Repo) {
        Write-Error "Could not detect repo. Pass -Repo owner/name or run from inside the repo."
        exit 1
    }
}

Write-Host "Setting up labels for $Repo..." -ForegroundColor Cyan

# Remove some defaults that overlap
$removeLabels = @("duplicate", "invalid", "question", "wontfix", "good first issue", "help wanted")
foreach ($label in $removeLabels) {
    gh label delete $label --repo $Repo --yes 2>$null
}

# Component labels
$components = @(
    @{ name = "component:api";            color = "1d76db"; description = ".NET API" },
    @{ name = "component:pipeline";       color = "0e8a16"; description = "Python processing pipeline" },
    @{ name = "component:web-ui";         color = "e99695"; description = "Svelte web UI" },
    @{ name = "component:infra";          color = "f9d0c4"; description = "Docker, database, MinIO" },
    @{ name = "component:docs";           color = "d4c5f9"; description = "Documentation" }
)

# Priority labels
$priorities = @(
    @{ name = "priority:critical";  color = "b60205"; description = "Must fix immediately" },
    @{ name = "priority:high";      color = "d93f0b"; description = "Fix before next release" },
    @{ name = "priority:medium";    color = "fbca04"; description = "Should fix soon" },
    @{ name = "priority:low";       color = "c2e0c6"; description = "Nice to have" }
)

# Type labels (keep built-in bug and enhancement, add others)
$types = @(
    @{ name = "security";       color = "ee0701"; description = "Security vulnerability or hardening" },
    @{ name = "testing";        color = "bfd4f2"; description = "Test coverage or test infrastructure" },
    @{ name = "performance";    color = "f7c6c7"; description = "Performance improvement" },
    @{ name = "tech-debt";      color = "fef2c0"; description = "Code quality or refactoring" },
    @{ name = "needs-triage";   color = "ededed"; description = "Needs review and categorization" }
)

$allLabels = $components + $priorities + $types

foreach ($label in $allLabels) {
    Write-Host "  Creating: $($label.name)" -ForegroundColor Gray
    gh label create $label.name --repo $Repo --color $label.color --description $label.description --force 2>$null
}

Write-Host "`nDone! Created $($allLabels.Count) labels." -ForegroundColor Green

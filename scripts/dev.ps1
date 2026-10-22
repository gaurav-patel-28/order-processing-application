param([ValidateSet('setup','up','seed','migrate','test','test-unit','test-integration','test-browser','lint','down','reset')][string]$Task = 'setup')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE" }
}

switch ($Task) {
    'setup' {
        Invoke-Checked docker @('compose','up','--build','-d','--wait')
        Invoke-Checked docker @('compose','exec','api','python','-m','app.seed')
    }
    'up' { Invoke-Checked docker @('compose','up','--build','-d','--wait') }
    'seed' { Invoke-Checked docker @('compose','exec','api','python','-m','app.seed') }
    'migrate' { Invoke-Checked docker @('compose','run','--rm','migrate') }
    'test' { Invoke-Checked docker @('compose','--profile','test','run','--build','--rm','tests') }
    'test-unit' { Invoke-Checked docker @('compose','--profile','test','run','--build','--rm','tests','pytest','-q','-m','not integration') }
    'test-integration' { Invoke-Checked docker @('compose','--profile','test','run','--build','--rm','tests','pytest','-q','-m','integration') }
    'test-browser' {
        Push-Location frontend
        try {
            Invoke-Checked npm.cmd @('ci')
            Invoke-Checked npx.cmd @('playwright','install','chromium')
            $previousBase = $env:E2E_BASE_URL
            try {
                $env:E2E_BASE_URL = 'http://localhost:8080'
                Invoke-Checked npm.cmd @('run','test:e2e')
            } finally { $env:E2E_BASE_URL = $previousBase }
        } finally { Pop-Location }
    }
    'lint' {
        Invoke-Checked docker @('compose','run','--rm','--no-deps','api','ruff','check','.')
        Invoke-Checked docker @('compose','run','--rm','--no-deps','api','ruff','format','--check','.')
        Push-Location frontend
        try {
            Invoke-Checked npm.cmd @('ci')
            Invoke-Checked npm.cmd @('run','format:check')
            Invoke-Checked npm.cmd @('run','build')
        } finally { Pop-Location }
    }
    'down' { Invoke-Checked docker @('compose','--profile','test','down') }
    'reset' {
        # Explicitly invoking reset authorizes removing this project's development volumes.
        Invoke-Checked docker @('compose','--profile','test','down','--volumes')
        & $PSCommandPath setup
    }
}

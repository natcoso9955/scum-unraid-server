param(
  [Parameter(Mandatory=$true)][string]$DockerHubUser,
  [Parameter(Mandatory=$true)][string]$SourceGitHubUser,
  [Parameter(Mandatory=$true)][string]$TemplateGitHubUser,
  [Parameter(Mandatory=$true)][string]$TemplateRepo,
  [string]$SourceRepo = 'scum-unraid-server',
  [string]$ImageTag = 'v0.1.0-rc1'
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Template = Join-Path $Root 'templates/scum-server.xml'
$Profile = Join-Path $Root 'ca_profile.xml'
$Xml = Get-Content -LiteralPath $Template -Raw
$Xml = $Xml.Replace('YOUR_DOCKERHUB_USERNAME', $DockerHubUser)
$Xml = $Xml.Replace('YOUR_GITHUB_USERNAME/scum-unraid-server', "$SourceGitHubUser/$SourceRepo")
$Xml = $Xml.Replace('YOUR_TEMPLATE_GITHUB_USERNAME/YOUR_TEMPLATE_REPO', "$TemplateGitHubUser/$TemplateRepo")
$Xml = $Xml.Replace('v0.1.0-rc1', $ImageTag)
[xml]$check = $Xml
[System.IO.File]::WriteAllText($Template, $Xml, [System.Text.UTF8Encoding]::new($false))
$Text = (Get-Content -LiteralPath $Profile -Raw).Replace('YOUR_GITHUB_USERNAME/scum-unraid-server', "$SourceGitHubUser/$SourceRepo")
[xml]$check = $Text
[System.IO.File]::WriteAllText($Profile, $Text, [System.Text.UTF8Encoding]::new($false))
Write-Host "Template configured: $Template"
Write-Host "Docker image: $DockerHubUser/scum-unraid:$ImageTag"
Write-Host "Template URL: https://raw.githubusercontent.com/$TemplateGitHubUser/$TemplateRepo/main/templates/scum-server.xml"
Write-Host 'NEXT: review XML and copy it into your EXISTING template repository. Never upload .env.'

# cosmosDb-postDeployPerms.ps1
param(
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroupName,

    [Parameter(Mandatory = $true)]
    [string]$CosmosDbUri
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($ResourceGroupName)) {
    throw "ResourceGroupName is required"
}

if ([string]::IsNullOrWhiteSpace($CosmosDbUri)) {
    throw "CosmosDbUri is required"
}

$accountMatch = [regex]::Match($CosmosDbUri, 'https://([^.]+)\.documents\..*')
if (-not $accountMatch.Success) {
    throw "Could not parse Cosmos DB account name from CosmosDbUri: $CosmosDbUri"
}

$accountName = $accountMatch.Groups[1].Value

Write-Host "==============================="
Write-Host "Cosmos DB Account Name: $accountName"

$upn = (az account show --query user.name -o tsv)
$objectId = (az ad signed-in-user show --query id -o tsv)
$subscriptionId = (az account show --query id -o tsv)

if ([string]::IsNullOrWhiteSpace($upn) -or [string]::IsNullOrWhiteSpace($objectId) -or [string]::IsNullOrWhiteSpace($subscriptionId)) {
    throw "Failed to resolve signed-in user or subscription context from Azure CLI"
}

$scope = "/subscriptions/$subscriptionId/resourceGroups/$ResourceGroupName/providers/Microsoft.DocumentDB/databaseAccounts/$accountName"

$roleName = "Contributor"
$roleId = (az role definition list --name $roleName --query "[0].id" -o tsv)
if ([string]::IsNullOrWhiteSpace($roleId)) {
    throw "Failed to resolve control-plane role id for '$roleName'"
}

Write-Host "Assigning role '$roleName' to user '$upn' on scope '$scope'..."
az role assignment create --assignee-object-id $objectId --assignee-principal-type "User" --role $roleId --scope $scope 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Control-plane role may already exist."
}

$dpRoleName = "Cosmos DB Built-in Data Contributor"
$dpRoleId = (az cosmosdb sql role definition list --account-name $accountName --resource-group $ResourceGroupName --query "[?roleName=='$dpRoleName'].id | [0]" -o tsv)
if ([string]::IsNullOrWhiteSpace($dpRoleId)) {
    throw "Failed to resolve data-plane role id for '$dpRoleName'"
}

Write-Host "Assigning data-plane role '$dpRoleName' to user '$upn' on Cosmos DB account '$accountName'..."
az cosmosdb sql role assignment create --account-name $accountName --resource-group $ResourceGroupName --scope "/" --principal-id $objectId --role-definition-id $dpRoleId 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Data-plane role may already exist."
}

Write-Host "Assigned Cosmos roles to $upn ($objectId)."
Write-Host "==============================="

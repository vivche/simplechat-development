// main.bicep
// Subscription-scope entry point for the AI Chief of Staff runtime (Phase 0).
// Pattern reused from vivche/security-plugin (proven GCC High Functions IaC):
//   creates the resource group, then deploys all resources via modules/resources.bicep.
targetScope = 'subscription'

@description('Name of the resource group to create')
param resourceGroupName string

@description('Azure region for all resources (GCC High: usgovvirginia)')
param location string = 'usgovvirginia'

@description('Short application name used to name resources (lowercase, no spaces)')
@maxLength(20)
param appName string = 'cos-runtime'

@description('Deployment environment tag')
@allowed(['dev', 'test', 'prod'])
param environment string = 'dev'

@description('App Service plan SKU. B1 (cheapest container-capable) for POC; EP1 (Elastic Premium) for scale-out.')
@allowed(['B1', 'EP1'])
param planSku string = 'B1'

// ── COS runtime configuration (surfaced as Function App settings) ──────────────
@description('Entra tenant ID that owns the cos-runtime-api app registration')
param cosTenantId string

@description('Client (application) ID of the cos-runtime-api app registration')
param cosClientId string

@description('API scope exposed by the runtime (used for On-Behalf-Of exchange)')
param cosApiScope string = 'api://${cosClientId}/access_as_user'

@description('Name of the Key Vault secret holding the app-registration client secret')
param clientSecretName string = 'cos-runtime-poc'

@description('Microsoft Graph base URL (GCC High sovereign endpoint)')
param graphBaseUrl string = 'https://graph.microsoft.us/v1.0'

@description('Entra authority host (GCC High sovereign endpoint)')
param authorityHost string = 'https://login.microsoftonline.us'

@description('Azure cloud name passed to the runtime')
param cloud string = 'usgovernment'

// ── Resource Group ────────────────────────────────────────────────────────────
resource rg 'Microsoft.Resources/resourceGroups@2023-07-01' = {
  name: resourceGroupName
  location: location
  tags: {
    environment: environment
    application: appName
  }
}

// ── Resources module (deployed into the resource group) ───────────────────────
module resources './modules/resources.bicep' = {
  name: 'resources-deployment'
  scope: rg
  params: {
    location: location
    appName: appName
    environment: environment
    planSku: planSku
    cosTenantId: cosTenantId
    cosClientId: cosClientId
    cosApiScope: cosApiScope
    clientSecretName: clientSecretName
    graphBaseUrl: graphBaseUrl
    authorityHost: authorityHost
    cloud: cloud
  }
}

// ── Outputs ───────────────────────────────────────────────────────────────────
output resourceGroupName string = rg.name
output functionAppName string = resources.outputs.functionAppName
output acrName string = resources.outputs.acrName
output acrLoginServer string = resources.outputs.acrLoginServer
output keyVaultName string = resources.outputs.keyVaultName
output managedIdentityClientId string = resources.outputs.managedIdentityClientId

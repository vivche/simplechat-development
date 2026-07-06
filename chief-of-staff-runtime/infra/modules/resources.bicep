// resources.bicep
// All resources for the AI Chief of Staff runtime (Phase 0).
// Reused from vivche/security-plugin with COS-specific additions:
//   - dedicated COS Key Vault (RBAC) that holds the app-registration client secret
//   - COS_* Function App settings, with COS_CLIENT_SECRET as a Key Vault reference
//   - secretless storage (managed-identity only), sovereign (GCC High) endpoints

// ── Parameters ────────────────────────────────────────────────────────────────
@description('Azure region for all resources')
param location string

@description('Short application name used to name resources')
@maxLength(20)
param appName string

@description('Deployment environment')
@allowed(['dev', 'test', 'prod'])
param environment string

@description('App Service plan SKU. B1 (Basic dedicated, cheapest container-capable) for POC; EP1 (Elastic Premium) for scale-out.')
@allowed(['B1', 'EP1'])
param planSku string = 'B1'

@description('Entra tenant ID that owns the cos-runtime-api app registration')
param cosTenantId string

@description('Client (application) ID of the cos-runtime-api app registration')
param cosClientId string

@description('API scope exposed by the runtime (used for On-Behalf-Of exchange)')
param cosApiScope string

@description('Name of the Key Vault secret holding the app-registration client secret')
param clientSecretName string

@description('Microsoft Graph base URL (GCC High sovereign endpoint)')
param graphBaseUrl string

@description('Entra authority host (GCC High sovereign endpoint)')
param authorityHost string

@description('Azure cloud name passed to the runtime')
param cloud string

// ── Naming ────────────────────────────────────────────────────────────────────
var suffix = take(uniqueString(resourceGroup().id), 6)
var safeName = toLower(replace(appName, '-', ''))

var names = {
  managedIdentity: 'id-${appName}-${environment}'
  logAnalytics: 'log-${appName}-${environment}'
  appInsights: 'appi-${appName}-${environment}'
  storageAccount: 'st${take(safeName, 12)}${suffix}'     // max 24 chars
  keyVault: 'kv-${take(safeName, 13)}-${suffix}'          // max 24 chars: 3+13+1+6=23
  acr: 'acr${take(safeName, 10)}${suffix}'               // max 50 chars
  appServicePlan: 'asp-${appName}-${environment}'
  functionApp: 'func-${appName}-${environment}'
}

// ── Role-definition IDs (built-in) ────────────────────────────────────────────
var roleIds = {
  acrPull: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
  keyVaultSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6'
  storageBlobDataOwner: 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
  storageQueueDataContributor: '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
  storageTableDataContributor: '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
}

// ── User-Assigned Managed Identity ───────────────────────────────────────────
resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: names.managedIdentity
  location: location
  tags: { environment: environment, application: appName }
}

// ── Log Analytics Workspace ───────────────────────────────────────────────────
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: names.logAnalytics
  location: location
  tags: { environment: environment, application: appName }
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// ── Application Insights (workspace-based) ────────────────────────────────────
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: names.appInsights
  location: location
  kind: 'web'
  tags: { environment: environment, application: appName }
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// ── Storage Account (Function App internal use) ────────────────────────────────
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: names.storageAccount
  location: location
  kind: 'StorageV2'
  tags: { environment: environment, application: appName }
  sku: { name: 'Standard_LRS' }
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false   // enforce managed-identity access only
  }
}

// ── Key Vault (RBAC-authorised, dedicated to the COS runtime) ─────────────────
// The app-registration client secret ('${clientSecretName}') is copied into this
// vault once, out of band. Bicep never stores the secret value.
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: names.keyVault
  location: location
  tags: { environment: environment, application: appName }
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enabledForTemplateDeployment: false
    publicNetworkAccess: 'Enabled'
  }
}

// ── Azure Container Registry ──────────────────────────────────────────────────
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: names.acr
  location: location
  tags: { environment: environment, application: appName }
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: true
    publicNetworkAccess: 'Enabled'
  }
}

// ── App Service Plan (Linux, supports custom containers) ──────────────────────
// B1 (Basic dedicated) is the cheapest SKU that can host a container Function App
// (~$13/mo). EP1 (Elastic Premium) adds elastic scale-out. Consumption/Y1 cannot
// run custom containers, so it is not an option here.
resource appServicePlan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: names.appServicePlan
  location: location
  kind: planSku == 'EP1' ? 'elastic' : 'linux'
  tags: { environment: environment, application: appName }
  sku: {
    name: planSku
    tier: planSku == 'EP1' ? 'ElasticPremium' : 'Basic'
  }
  properties: {
    reserved: true                  // required for Linux
    maximumElasticWorkerCount: planSku == 'EP1' ? 20 : null
  }
}

// ── Function App (Linux container) ────────────────────────────────────────────
resource functionApp 'Microsoft.Web/sites@2023-12-01' = {
  name: names.functionApp
  location: location
  kind: 'functionapp,linux,container'
  tags: { environment: environment, application: appName }
  identity: {
    type: 'SystemAssigned, UserAssigned'
    userAssignedIdentities: {
      '${managedIdentity.id}': {}
    }
  }
  properties: {
    serverFarmId: appServicePlan.id
    reserved: true
    httpsOnly: true
    siteConfig: {
      // Point to our ACR image; tag updated to the specific SHA by the deploy workflow
      linuxFxVersion: 'DOCKER|${acr.properties.loginServer}/${appName}:latest'
      // Pull from ACR using the system-assigned managed identity
      acrUseManagedIdentityCreds: true
      minTlsVersion: '1.2'
      ftpsState: 'Disabled'
      // Basic/dedicated plans idle out HTTP triggers without alwaysOn; not applicable to Elastic Premium.
      alwaysOn: planSku == 'EP1' ? null : true
      appSettings: [
        // Storage – explicit service URIs so the runtime resolves sovereign-cloud
        // endpoints (*.core.usgovcloudapi.net, not *.core.windows.net)
        { name: 'AzureWebJobsStorage__blobServiceUri',  value: storageAccount.properties.primaryEndpoints.blob }
        { name: 'AzureWebJobsStorage__queueServiceUri', value: storageAccount.properties.primaryEndpoints.queue }
        { name: 'AzureWebJobsStorage__tableServiceUri', value: storageAccount.properties.primaryEndpoints.table }
        { name: 'AzureWebJobsStorage__credential',      value: 'managedidentity' }
        { name: 'AzureWebJobsStorage__clientId',        value: managedIdentity.properties.clientId }
        // Functions runtime
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME',    value: 'python' }
        // Application Insights
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
        // ACR
        { name: 'DOCKER_REGISTRY_SERVER_URL', value: 'https://${acr.properties.loginServer}' }
        // ── COS runtime configuration ──────────────────────────────────────────
        { name: 'COS_TENANT_ID',        value: cosTenantId }
        { name: 'COS_CLIENT_ID',        value: cosClientId }
        { name: 'COS_API_SCOPE',        value: cosApiScope }
        { name: 'COS_GRAPH_BASE_URL',   value: graphBaseUrl }
        { name: 'COS_AUTHORITY_HOST',   value: authorityHost }
        { name: 'COS_CLOUD',            value: cloud }
        { name: 'COS_USE_IN_MEMORY_STORES', value: 'true' }
        // Client secret pulled from the dedicated COS Key Vault at runtime.
        // Resolves once the secret is added and the MI has Key Vault Secrets User.
        { name: 'COS_CLIENT_SECRET', value: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/${clientSecretName})' }
      ]
    }
  }
  dependsOn: [
    acrPullRole
    storageBlobRole
    storageQueueRole
    storageTableRole
    kvSecretsUserRole
  ]
}

// ── Role Assignments ──────────────────────────────────────────────────────────

// ACR Pull – user-assigned identity (kept for completeness)
resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, managedIdentity.id, roleIds.acrPull)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.acrPull)
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ACR Pull – system-assigned identity (used by Deployment Center)
resource acrPullRoleSystem 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, functionApp.id, roleIds.acrPull)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.acrPull)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Key Vault Secrets User – read the client secret at runtime
resource kvSecretsUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, managedIdentity.id, roleIds.keyVaultSecretsUser)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.keyVaultSecretsUser)
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Storage Blob Data Owner – required by Azure Functions for checkpoint storage
resource storageBlobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, managedIdentity.id, roleIds.storageBlobDataOwner)
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.storageBlobDataOwner)
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Storage Queue Data Contributor – required by Azure Functions runtime
resource storageQueueRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, managedIdentity.id, roleIds.storageQueueDataContributor)
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.storageQueueDataContributor)
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Storage Table Data Contributor – required by Azure Functions runtime
resource storageTableRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, managedIdentity.id, roleIds.storageTableDataContributor)
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleIds.storageTableDataContributor)
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Outputs ───────────────────────────────────────────────────────────────────
output functionAppName string = functionApp.name
output acrName string = acr.name
output acrLoginServer string = acr.properties.loginServer
output keyVaultName string = keyVault.name
output appInsightsName string = appInsights.name
output storageAccountName string = storageAccount.name
output managedIdentityClientId string = managedIdentity.properties.clientId

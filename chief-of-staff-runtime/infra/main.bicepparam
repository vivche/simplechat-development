using './main.bicep'

param resourceGroupName = 'cos-runtime-dev-rg'
param location          = 'usgovvirginia'
param appName           = 'cos-runtime'
param environment       = 'dev'
param planSku           = 'B1'   // cheapest container-capable SKU; set 'EP1' for elastic scale-out

// ── COS runtime configuration (non-secret) ─────────────────────────────────────
param cosTenantId       = '03f141f3-496d-4319-bbea-a3e9286cab10'
param cosClientId       = 'bed646c0-7953-4871-8b74-456a5883c283'
param cosApiScope       = 'api://bed646c0-7953-4871-8b74-456a5883c283/access_as_user'
param clientSecretName  = 'cos-runtime-poc'
param graphBaseUrl      = 'https://graph.microsoft.us/v1.0'
param authorityHost     = 'https://login.microsoftonline.us'
param cloud             = 'usgovernment'

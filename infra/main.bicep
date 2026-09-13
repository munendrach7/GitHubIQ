targetScope = 'resourceGroup'

@description('Name prefix for all resources.')
param namePrefix string = 'giq'

@description('Location for all resources.')
param location string = resourceGroup().location

@description('Azure OpenAI model to deploy.')
param openAiModel string = 'gpt-4o-mini'

@description('Azure OpenAI model version.')
param openAiModelVersion string = '2024-07-18'

@description('Container image for the backend (set by azd / CI).')
param backendImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Container image for the frontend (set by azd / CI).')
param frontendImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

var suffix = uniqueString(resourceGroup().id)
var tags = { project: 'githubiq', env: 'mvp' }

// ---------------------------------------------------------------------------
// Observability
// ---------------------------------------------------------------------------
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${namePrefix}-logs-${suffix}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// ---------------------------------------------------------------------------
// Azure AI Foundry (Azure OpenAI) + model deployment
// ---------------------------------------------------------------------------
resource aiServices 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: '${namePrefix}-aoai-${suffix}'
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: '${namePrefix}-aoai-${suffix}'
    publicNetworkAccess: 'Enabled'
  }
}

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: aiServices
  name: openAiModel
  sku: { name: 'GlobalStandard', capacity: 30 }
  properties: {
    model: {
      format: 'OpenAI'
      name: openAiModel
      version: openAiModelVersion
    }
  }
}

// ---------------------------------------------------------------------------
// Cosmos DB (serverless, document store for analysis results)
// ---------------------------------------------------------------------------
resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: '${namePrefix}-cosmos-${suffix}'
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    enableFreeTier: false
    capabilities: [ { name: 'EnableServerless' } ]
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
    locations: [ { locationName: location, failoverPriority: 0 } ]
  }
}

resource cosmosDb 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-11-15' = {
  parent: cosmos
  name: 'githubiq'
  properties: { resource: { id: 'githubiq' } }
}

resource cosmosContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15' = {
  parent: cosmosDb
  name: 'analyses'
  properties: {
    resource: {
      id: 'analyses'
      partitionKey: { paths: [ '/id' ], kind: 'Hash' }
    }
  }
}

// ---------------------------------------------------------------------------
// Container Apps environment
// ---------------------------------------------------------------------------
resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${namePrefix}-env-${suffix}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

var cosmosKey = cosmos.listKeys().primaryMasterKey
var aoaiKey = aiServices.listKeys().key1

resource backendApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namePrefix}-backend'
  location: location
  tags: union(tags, { 'azd-service-name': 'backend' })
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      ingress: { external: true, targetPort: 8000, transport: 'auto' }
      secrets: [
        { name: 'aoai-key', value: aoaiKey }
        { name: 'cosmos-key', value: cosmosKey }
      ]
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: backendImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'ENVIRONMENT', value: 'production' }
            { name: 'CORS_ORIGINS', value: '*' }
            { name: 'AZURE_OPENAI_ENDPOINT', value: aiServices.properties.endpoint }
            { name: 'AZURE_OPENAI_API_KEY', secretRef: 'aoai-key' }
            { name: 'AZURE_OPENAI_DEPLOYMENT', value: openAiModel }
            { name: 'AZURE_OPENAI_API_VERSION', value: '2024-10-21' }
            { name: 'COSMOS_ENDPOINT', value: cosmos.properties.documentEndpoint }
            { name: 'COSMOS_KEY', secretRef: 'cosmos-key' }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
}

resource frontendApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namePrefix}-frontend'
  location: location
  tags: union(tags, { 'azd-service-name': 'frontend' })
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      ingress: { external: true, targetPort: 80, transport: 'auto' }
    }
    template: {
      containers: [
        {
          name: 'frontend'
          image: frontendImage
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: [
            { name: 'BACKEND_URL', value: 'https://${backendApp.properties.configuration.ingress.fqdn}' }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 2 }
    }
  }
}

output AZURE_OPENAI_ENDPOINT string = aiServices.properties.endpoint
output AZURE_OPENAI_DEPLOYMENT string = openAiModel
output COSMOS_ENDPOINT string = cosmos.properties.documentEndpoint
output BACKEND_FQDN string = backendApp.properties.configuration.ingress.fqdn
output FRONTEND_URL string = 'https://${frontendApp.properties.configuration.ingress.fqdn}'

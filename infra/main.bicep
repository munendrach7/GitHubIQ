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

// Built-in role definition ids used for managed-identity (keyless) data access.
var roleOpenAiUser = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd') // Cognitive Services OpenAI User
var roleServiceBusOwner = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '090c5cfd-751d-490a-894a-3ce6f1109419') // Azure Service Bus Data Owner

// ---------------------------------------------------------------------------
// User-assigned managed identity — the app's single workload identity used to
// authenticate to Azure OpenAI, Cosmos DB and Service Bus without any secrets.
// ---------------------------------------------------------------------------
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-id-${suffix}'
  location: location
  tags: tags
}

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
// Service Bus — async job queue between the API and the worker(s)
// ---------------------------------------------------------------------------
resource serviceBus 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: '${namePrefix}-sb-${suffix}'
  location: location
  tags: tags
  sku: { name: 'Standard', tier: 'Standard' }
  properties: { disableLocalAuth: true }
}

resource sbQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBus
  name: 'analysis-jobs'
  properties: {
    lockDuration: 'PT5M'
    maxDeliveryCount: 3
    deadLetteringOnMessageExpiration: true
  }
}

// ---------------------------------------------------------------------------
// Role assignments — grant the workload identity keyless data-plane access.
// ---------------------------------------------------------------------------
resource raOpenAi 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiServices.id, identity.id, 'openai-user')
  scope: aiServices
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: roleOpenAiUser
  }
}

resource raServiceBus 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(serviceBus.id, identity.id, 'sb-owner')
  scope: serviceBus
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: roleServiceBusOwner
  }
}

// Cosmos DB uses its own SQL (data-plane) RBAC — assign the Built-in Data
// Contributor role (id ...0002) to the workload identity over the account.
resource raCosmos 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-11-15' = {
  parent: cosmos
  name: guid(cosmos.id, identity.id, 'cosmos-data-contrib')
  properties: {
    principalId: identity.properties.principalId
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
    scope: cosmos.id
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

var sbNamespaceFqdn = '${serviceBus.name}.servicebus.windows.net'
var commonAppEnv = [
  { name: 'ENVIRONMENT', value: 'production' }
  { name: 'USE_MANAGED_IDENTITY', value: 'true' }
  { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
  { name: 'AZURE_OPENAI_ENDPOINT', value: aiServices.properties.endpoint }
  { name: 'AZURE_OPENAI_DEPLOYMENT', value: openAiModel }
  { name: 'AZURE_OPENAI_API_VERSION', value: '2024-10-21' }
  { name: 'COSMOS_ENDPOINT', value: cosmos.properties.documentEndpoint }
  { name: 'SERVICEBUS_NAMESPACE', value: sbNamespaceFqdn }
  { name: 'SERVICEBUS_QUEUE', value: 'analysis-jobs' }
]

resource backendApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namePrefix}-backend'
  location: location
  tags: union(tags, { 'azd-service-name': 'backend' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      ingress: { external: true, targetPort: 8000, transport: 'auto' }
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: backendImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: union(commonAppEnv, [ { name: 'CORS_ORIGINS', value: '*' } ])
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
  dependsOn: [ raOpenAi, raServiceBus, raCosmos ]
}

// Async worker — same image, runs the Service Bus consumer instead of uvicorn.
// No ingress; scales on its own (add KEDA queue-length scaling as needed).
resource workerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namePrefix}-worker'
  location: location
  tags: union(tags, { 'azd-service-name': 'worker' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
    }
    template: {
      containers: [
        {
          name: 'worker'
          image: backendImage
          command: [ 'python', '-m', 'app.worker' ]
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: commonAppEnv
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 5 }
    }
  }
  dependsOn: [ raOpenAi, raServiceBus, raCosmos ]
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
output SERVICEBUS_NAMESPACE string = sbNamespaceFqdn
output AZURE_CLIENT_ID string = identity.properties.clientId
output BACKEND_FQDN string = backendApp.properties.configuration.ingress.fqdn
output FRONTEND_URL string = 'https://${frontendApp.properties.configuration.ingress.fqdn}'

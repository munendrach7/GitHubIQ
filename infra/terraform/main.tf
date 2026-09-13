data "azurerm_client_config" "current" {}

# The resource group is a prerequisite (created by the CI workflow / az), matching
# the original Bicep model where the deployment targets an existing RG.
data "azurerm_resource_group" "rg" {
  name = var.resource_group_name
}

locals {
  # Deterministic, stable suffix (mirrors the Bicep uniqueString) derived from the
  # subscription + resource group so names are unique per environment.
  suffix = substr(sha1("${data.azurerm_client_config.current.subscription_id}/${var.resource_group_name}"), 0, 13)

  tags = {
    project = "githubiq"
    env     = "mvp"
  }

  sb_fqdn = "${azurerm_servicebus_namespace.sb.name}.servicebus.windows.net"

  # Shared app configuration (keyless — every Azure dependency is reached via the
  # user-assigned managed identity). Consumed by the backend and the worker.
  common_env = [
    { name = "ENVIRONMENT", value = "production" },
    { name = "USE_MANAGED_IDENTITY", value = "true" },
    { name = "AZURE_CLIENT_ID", value = azurerm_user_assigned_identity.app.client_id },
    { name = "AZURE_OPENAI_ENDPOINT", value = azurerm_cognitive_account.aoai.endpoint },
    { name = "AZURE_OPENAI_DEPLOYMENT", value = var.openai_model },
    { name = "AZURE_OPENAI_API_VERSION", value = "2024-10-21" },
    { name = "COSMOS_ENDPOINT", value = azurerm_cosmosdb_account.cosmos.endpoint },
    { name = "SERVICEBUS_NAMESPACE", value = local.sb_fqdn },
    { name = "SERVICEBUS_QUEUE", value = "analysis-jobs" },
  ]
}

# ---------------------------------------------------------------------------
# Workload identity — the app's single credential for OpenAI, Cosmos & Service Bus.
# ---------------------------------------------------------------------------
resource "azurerm_user_assigned_identity" "app" {
  name                = "${var.name_prefix}-id-${local.suffix}"
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name
  tags                = local.tags
}

# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------
resource "azurerm_log_analytics_workspace" "logs" {
  name                = "${var.name_prefix}-logs-${local.suffix}"
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

# ---------------------------------------------------------------------------
# Azure AI Foundry (Azure OpenAI) + model deployment
# ---------------------------------------------------------------------------
resource "azurerm_cognitive_account" "aoai" {
  name                          = "${var.name_prefix}-aoai-${local.suffix}"
  location                      = data.azurerm_resource_group.rg.location
  resource_group_name           = data.azurerm_resource_group.rg.name
  kind                          = "AIServices"
  sku_name                      = "S0"
  custom_subdomain_name         = "${var.name_prefix}-aoai-${local.suffix}"
  public_network_access_enabled = true
  tags                          = local.tags
}

resource "azurerm_cognitive_deployment" "model" {
  name                 = var.openai_model
  cognitive_account_id = azurerm_cognitive_account.aoai.id

  model {
    format  = "OpenAI"
    name    = var.openai_model
    version = var.openai_model_version
  }

  sku {
    name     = "GlobalStandard"
    capacity = var.openai_capacity
  }
}

# ---------------------------------------------------------------------------
# Cosmos DB (serverless document store for analysis results)
# ---------------------------------------------------------------------------
resource "azurerm_cosmosdb_account" "cosmos" {
  name                = "${var.name_prefix}-cosmos-${local.suffix}"
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"
  free_tier_enabled   = false
  tags                = local.tags

  capabilities {
    name = "EnableServerless"
  }

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = data.azurerm_resource_group.rg.location
    failover_priority = 0
  }
}

resource "azurerm_cosmosdb_sql_database" "db" {
  name                = "githubiq"
  resource_group_name = data.azurerm_resource_group.rg.name
  account_name        = azurerm_cosmosdb_account.cosmos.name
}

resource "azurerm_cosmosdb_sql_container" "analyses" {
  name                = "analyses"
  resource_group_name = data.azurerm_resource_group.rg.name
  account_name        = azurerm_cosmosdb_account.cosmos.name
  database_name       = azurerm_cosmosdb_sql_database.db.name
  partition_key_paths = ["/id"]
}

resource "azurerm_cosmosdb_sql_container" "users" {
  name                = "users"
  resource_group_name = data.azurerm_resource_group.rg.name
  account_name        = azurerm_cosmosdb_account.cosmos.name
  database_name       = azurerm_cosmosdb_sql_database.db.name
  partition_key_paths = ["/id"]
}

# ---------------------------------------------------------------------------
# Service Bus — async job queue between the API and the worker(s). Keyless:
# local (SAS) auth is disabled, so every client authenticates with Entra.
# ---------------------------------------------------------------------------
resource "azurerm_servicebus_namespace" "sb" {
  name                = "${var.name_prefix}-sb-${local.suffix}"
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name
  sku                 = "Standard"
  local_auth_enabled  = false
  tags                = local.tags
}

resource "azurerm_servicebus_queue" "jobs" {
  name         = "analysis-jobs"
  namespace_id = azurerm_servicebus_namespace.sb.id

  lock_duration                        = "PT5M"
  max_delivery_count                   = 3
  dead_lettering_on_message_expiration = true
}

# ---------------------------------------------------------------------------
# Role assignments — grant the workload identity keyless data-plane access.
# ---------------------------------------------------------------------------
resource "azurerm_role_assignment" "openai_user" {
  scope                = azurerm_cognitive_account.aoai.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

resource "azurerm_role_assignment" "sb_owner" {
  scope                = azurerm_servicebus_namespace.sb.id
  role_definition_name = "Azure Service Bus Data Owner"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# Cosmos DB uses its own SQL (data-plane) RBAC — Built-in Data Contributor (…0002).
resource "azurerm_cosmosdb_sql_role_assignment" "cosmos_contrib" {
  resource_group_name = data.azurerm_resource_group.rg.name
  account_name        = azurerm_cosmosdb_account.cosmos.name
  role_definition_id  = "${azurerm_cosmosdb_account.cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = azurerm_user_assigned_identity.app.principal_id
  scope               = azurerm_cosmosdb_account.cosmos.id
}

# ---------------------------------------------------------------------------
# Container Registry — holds the app images the Container Apps pull via identity.
# ---------------------------------------------------------------------------
resource "azurerm_container_registry" "acr" {
  name                = "${var.name_prefix}acr${local.suffix}"
  resource_group_name = data.azurerm_resource_group.rg.name
  location            = data.azurerm_resource_group.rg.location
  sku                 = "Basic"
  admin_enabled       = false
  tags                = local.tags
}

resource "azurerm_role_assignment" "acr_pull" {
  scope                = azurerm_container_registry.acr.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# ---------------------------------------------------------------------------
# Container Apps environment
# ---------------------------------------------------------------------------
resource "azurerm_container_app_environment" "env" {
  name                       = "${var.name_prefix}-env-${local.suffix}"
  location                   = data.azurerm_resource_group.rg.location
  resource_group_name        = data.azurerm_resource_group.rg.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.logs.id
  tags                       = local.tags
}

resource "azurerm_container_app" "backend" {
  name                         = "${var.name_prefix}-backend"
  resource_group_name          = data.azurerm_resource_group.rg.name
  container_app_environment_id = azurerm_container_app_environment.env.id
  revision_mode                = "Single"
  tags                         = merge(local.tags, { "azd-service-name" = "backend" })

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = azurerm_container_registry.acr.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  # Azure Speech (TTS) key for video narration, from the multi-service AIServices account.
  secret {
    name  = "speech-key"
    value = azurerm_cognitive_account.aoai.primary_access_key
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 1
    max_replicas = 3

    container {
      name   = "backend"
      image  = var.backend_image
      cpu    = 0.5
      memory = "1Gi"

      dynamic "env" {
        for_each = local.common_env
        content {
          name  = env.value.name
          value = env.value.value
        }
      }

      env {
        name  = "CORS_ORIGINS"
        value = "*"
      }

      env {
        name        = "SPEECH_KEY"
        secret_name = "speech-key"
      }

      env {
        name  = "SPEECH_REGION"
        value = data.azurerm_resource_group.rg.location
      }
    }
  }

  depends_on = [
    azurerm_role_assignment.openai_user,
    azurerm_role_assignment.sb_owner,
    azurerm_role_assignment.acr_pull,
    azurerm_cosmosdb_sql_role_assignment.cosmos_contrib,
  ]

  # The app-deploy pipeline rolls out real images out-of-band; don't revert them.
  lifecycle {
    ignore_changes = [template[0].container[0].image]
  }
}

# Async worker — same image, runs the Service Bus consumer instead of uvicorn.
# No ingress; scales 0→N on queue depth via a KEDA azure-servicebus scaler that
# authenticates with the same user-assigned identity (keyless). Uses azapi so the
# scale-rule managed identity is expressed exactly (azurerm can't yet).
resource "azapi_resource" "worker" {
  type      = "Microsoft.App/containerApps@2024-10-02-preview"
  name      = "${var.name_prefix}-worker"
  parent_id = data.azurerm_resource_group.rg.id
  location  = data.azurerm_resource_group.rg.location
  tags      = merge(local.tags, { "azd-service-name" = "worker" })

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  body = {
    properties = {
      managedEnvironmentId = azurerm_container_app_environment.env.id
      configuration = {
        activeRevisionsMode = "Single"
        registries = [
          {
            server   = azurerm_container_registry.acr.login_server
            identity = azurerm_user_assigned_identity.app.id
          }
        ]
      }
      template = {
        containers = [
          {
            name    = "worker"
            image   = var.backend_image
            command = ["python", "-m", "app.worker"]
            resources = {
              cpu    = 0.5
              memory = "1Gi"
            }
            env = local.common_env
          }
        ]
        scale = {
          minReplicas = 0
          maxReplicas = 5
          rules = [
            {
              name = "servicebus-queue-depth"
              custom = {
                type     = "azure-servicebus"
                identity = azurerm_user_assigned_identity.app.id
                metadata = {
                  namespace    = azurerm_servicebus_namespace.sb.name
                  queueName    = "analysis-jobs"
                  messageCount = "1"
                }
              }
            }
          ]
        }
      }
    }
  }

  depends_on = [
    azurerm_role_assignment.openai_user,
    azurerm_role_assignment.sb_owner,
    azurerm_role_assignment.acr_pull,
    azurerm_cosmosdb_sql_role_assignment.cosmos_contrib,
  ]

  # The app-deploy pipeline updates the worker image out-of-band; ignore that drift.
  lifecycle {
    ignore_changes = [body]
  }
}

resource "azurerm_container_app" "frontend" {
  name                         = "${var.name_prefix}-frontend"
  resource_group_name          = data.azurerm_resource_group.rg.name
  container_app_environment_id = azurerm_container_app_environment.env.id
  revision_mode                = "Single"
  tags                         = merge(local.tags, { "azd-service-name" = "frontend" })

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = azurerm_container_registry.acr.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  ingress {
    external_enabled = true
    target_port      = 80
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 1
    max_replicas = 2

    container {
      name   = "frontend"
      image  = var.frontend_image
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name  = "BACKEND_URL"
        value = "https://${azurerm_container_app.backend.ingress[0].fqdn}"
      }
    }
  }

  depends_on = [azurerm_role_assignment.acr_pull]

  # The app-deploy pipeline rolls out real images out-of-band; don't revert them.
  lifecycle {
    ignore_changes = [template[0].container[0].image]
  }
}

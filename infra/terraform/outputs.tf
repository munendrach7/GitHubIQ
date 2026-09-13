output "AZURE_OPENAI_ENDPOINT" {
  value = azurerm_cognitive_account.aoai.endpoint
}

output "AZURE_OPENAI_DEPLOYMENT" {
  value = var.openai_model
}

output "COSMOS_ENDPOINT" {
  value = azurerm_cosmosdb_account.cosmos.endpoint
}

output "SERVICEBUS_NAMESPACE" {
  value = local.sb_fqdn
}

output "AZURE_CLIENT_ID" {
  value = azurerm_user_assigned_identity.app.client_id
}

output "BACKEND_FQDN" {
  value = azurerm_container_app.backend.ingress[0].fqdn
}

output "FRONTEND_URL" {
  value = "https://${azurerm_container_app.frontend.ingress[0].fqdn}"
}

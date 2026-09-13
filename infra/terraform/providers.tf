provider "azurerm" {
  features {}
  # Subscription is taken from ARM_SUBSCRIPTION_ID (CI) or the logged-in az CLI.
}

provider "azapi" {}

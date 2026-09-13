terraform {
  required_version = ">= 1.6"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.0"
    }
  }

  # Remote state lives in an Azure Storage container. The concrete values are
  # supplied at `terraform init` time via -backend-config (see the CI workflow),
  # so this project can be initialised against any subscription/state account.
  backend "azurerm" {}
}

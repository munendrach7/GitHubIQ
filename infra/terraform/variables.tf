variable "resource_group_name" {
  type        = string
  default     = "rg-githubiq"
  description = "Resource group that holds all GitHubIQ resources."
}

variable "location" {
  type        = string
  default     = "eastus2"
  description = "Azure region for all resources."
}

variable "name_prefix" {
  type        = string
  default     = "giq"
  description = "Short prefix used when naming resources."
}

variable "openai_model" {
  type        = string
  default     = "gpt-4.1-mini"
  description = "Azure OpenAI model to deploy (also used as the deployment name)."
}

variable "openai_model_version" {
  type        = string
  default     = "2025-04-14"
  description = "Azure OpenAI model version."
}

variable "openai_capacity" {
  type        = number
  default     = 30
  description = "GlobalStandard capacity (TPM in thousands) for the model deployment."
}

variable "backend_image" {
  type        = string
  default     = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"
  description = "Container image for the backend + worker (set by CI after ACR build)."
}

variable "frontend_image" {
  type        = string
  default     = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"
  description = "Container image for the frontend (set by CI after ACR build)."
}

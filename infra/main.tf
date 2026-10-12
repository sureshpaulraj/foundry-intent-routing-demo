terraform {
  required_version = ">= 1.6"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.0"
    }
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.0"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id
}

provider "azuread" {
  tenant_id = var.tenant_id
}

provider "azapi" {}

variable "subscription_id" {
  type        = string
  description = "Subscription where the demo is provisioned."
}

variable "tenant_id" {
  type        = string
  description = "Tenant allowed to sign in."
}

variable "name_suffix" {
  type        = string
  description = "Unique, lower-case suffix for globally named resources."
  default     = "demo123"
}

variable "location" {
  type    = string
  default = "eastus2"
}

variable "enable_app" {
  type    = bool
  default = false
}

variable "enable_public_ingress" {
  type    = bool
  default = false
}

variable "image_tag" {
  type    = string
  default = "v1"
}

data "azuread_client_config" "current" {}

resource "azurerm_resource_group" "demo" {
  name     = "rg-intent-demo-${var.name_suffix}"
  location = var.location
}

resource "azurerm_cognitive_account" "foundry" {
  name                       = "ai-intentdemo-${var.name_suffix}"
  location                   = azurerm_resource_group.demo.location
  resource_group_name        = azurerm_resource_group.demo.name
  kind                       = "AIServices"
  sku_name                   = "S0"
  project_management_enabled = true
  custom_subdomain_name      = "ai-intentdemo-${var.name_suffix}"
  local_auth_enabled         = false

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_cognitive_account_project" "demo" {
  name                 = "intent-router"
  cognitive_account_id = azurerm_cognitive_account.foundry.id
  location             = var.location
  description          = "Synthetic LLM versus deterministic intent routing demo"
  display_name         = "Intent Router Demo"

  identity {
    type = "SystemAssigned"
  }

  depends_on = [azurerm_cognitive_deployment.generation]
}

resource "azurerm_cognitive_deployment" "decision" {
  name                 = "intent-decision"
  cognitive_account_id = azurerm_cognitive_account.foundry.id
  model {
    format  = "Microsoft"
    name    = "Microsoft-Decision-1"
    version = "1"
  }
  sku {
    name     = "GlobalStandard"
    capacity = 5
  }
}

resource "azurerm_cognitive_deployment" "generation" {
  name                 = "gpt-4-1-mini"
  cognitive_account_id = azurerm_cognitive_account.foundry.id
  model {
    format  = "OpenAI"
    name    = "gpt-4.1-mini"
    version = "2025-04-14"
  }
  sku {
    name     = "GlobalStandard"
    capacity = 10
  }

  depends_on = [azurerm_cognitive_deployment.decision]
}

resource "azurerm_container_registry" "demo" {
  name                = "acintentdemo${var.name_suffix}"
  resource_group_name = azurerm_resource_group.demo.name
  location            = azurerm_resource_group.demo.location
  sku                 = "Basic"
  admin_enabled       = false
}

resource "azurerm_container_app_environment" "demo" {
  name                  = "cae-intent-demo-${var.name_suffix}"
  resource_group_name   = azurerm_resource_group.demo.name
  location              = azurerm_resource_group.demo.location
  public_network_access = "Enabled"
}

resource "azurerm_user_assigned_identity" "pull" {
  name                = "id-intent-pull-${var.name_suffix}"
  resource_group_name = azurerm_resource_group.demo.name
  location            = azurerm_resource_group.demo.location
}

resource "azurerm_role_assignment" "image_pull" {
  scope                = azurerm_container_registry.demo.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.pull.principal_id
}

resource "azuread_application" "demo" {
  display_name     = "Foundry Intent Router Demo ${var.name_suffix}"
  sign_in_audience = "AzureADMyOrg"
  owners           = [data.azuread_client_config.current.object_id]
  web {
    redirect_uris = ["https://ca-intent-demo-${var.name_suffix}.${azurerm_container_app_environment.demo.default_domain}/.auth/login/aad/callback"]
  }
}

resource "azuread_service_principal" "demo" {
  client_id                    = azuread_application.demo.client_id
  app_role_assignment_required = true
  owners                       = [data.azuread_client_config.current.object_id]
}

resource "azuread_app_role_assignment" "owner" {
  app_role_id         = "00000000-0000-0000-0000-000000000000"
  principal_object_id = data.azuread_client_config.current.object_id
  resource_object_id  = azuread_service_principal.demo.object_id
}

resource "azuread_application_password" "demo" {
  application_id = azuread_application.demo.id
  display_name   = "App Service Easy Auth"
}

resource "azurerm_container_app" "demo" {
  count                        = var.enable_app ? 1 : 0
  name                         = "ca-intent-demo-${var.name_suffix}"
  resource_group_name          = azurerm_resource_group.demo.name
  container_app_environment_id = azurerm_container_app_environment.demo.id
  revision_mode                = "Single"

  identity {
    type         = "SystemAssigned, UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.pull.id]
  }
  registry {
    server   = azurerm_container_registry.demo.login_server
    identity = azurerm_user_assigned_identity.pull.id
  }
  secret {
    name  = "entra-client-secret"
    value = azuread_application_password.demo.value
  }
  template {
    min_replicas = 0
    max_replicas = 1
    container {
      name   = "intent-router"
      image  = "${azurerm_container_registry.demo.login_server}/intent-demo:${var.image_tag}"
      cpu    = 0.25
      memory = "0.5Gi"
      env {
        name  = "FOUNDRY_ENDPOINT"
        value = "https://${azurerm_cognitive_account.foundry.name}.services.ai.azure.com/"
      }
      env {
        name  = "DECISION_DEPLOYMENT"
        value = azurerm_cognitive_deployment.decision.name
      }
      env {
        name  = "GENERATION_DEPLOYMENT"
        value = azurerm_cognitive_deployment.generation.name
      }
    }
  }
  ingress {
    external_enabled = var.enable_public_ingress
    target_port      = 8000
    transport        = "http"
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  depends_on = [azurerm_role_assignment.image_pull]
}

resource "azapi_resource" "auth" {
  count     = var.enable_app ? 1 : 0
  type      = "Microsoft.App/containerApps/authConfigs@2024-03-01"
  name      = "current"
  parent_id = azurerm_container_app.demo[0].id
  body = {
    properties = {
      platform = { enabled = true }
      globalValidation = {
        unauthenticatedClientAction = "RedirectToLoginPage"
        redirectToProvider          = "azureActiveDirectory"
      }
      httpSettings = { requireHttps = true }
      identityProviders = {
        azureActiveDirectory = {
          enabled = true
          registration = {
            clientId                = azuread_application.demo.client_id
            clientSecretSettingName = "entra-client-secret"
            openIdIssuer            = "https://login.microsoftonline.com/${var.tenant_id}/v2.0"
          }
          validation = {
            defaultAuthorizationPolicy = {
              allowedPrincipals = {
                identities = [data.azuread_client_config.current.object_id]
              }
            }
          }
        }
      }
      login = {
        tokenStore = { enabled = false }
      }
    }
  }
}

resource "azurerm_role_assignment" "model_inference" {
  count                = var.enable_app ? 1 : 0
  scope                = azurerm_cognitive_account.foundry.id
  role_definition_name = "Cognitive Services User"
  principal_id         = azurerm_container_app.demo[0].identity[0].principal_id
}

resource "azurerm_role_assignment" "owner_inference" {
  scope                = azurerm_cognitive_account.foundry.id
  role_definition_name = "Cognitive Services User"
  principal_id         = data.azuread_client_config.current.object_id
}

resource "azurerm_role_definition" "decision_inference" {
  name        = "Intent Decision API Caller ${var.name_suffix}"
  scope       = azurerm_resource_group.demo.id
  description = "Invoke the Microsoft-Decision-1 provider endpoint."
  permissions {
    actions      = ["Microsoft.CognitiveServices/accounts/read"]
    data_actions = ["Microsoft.CognitiveServices/accounts/AIServices/providers/action"]
  }
  assignable_scopes = [azurerm_resource_group.demo.id]
}

resource "azurerm_role_assignment" "owner_decision" {
  scope              = azurerm_cognitive_account.foundry.id
  role_definition_id = azurerm_role_definition.decision_inference.role_definition_resource_id
  principal_id       = data.azuread_client_config.current.object_id
}

resource "azurerm_role_assignment" "app_decision" {
  count              = var.enable_app ? 1 : 0
  scope              = azurerm_cognitive_account.foundry.id
  role_definition_id = azurerm_role_definition.decision_inference.role_definition_resource_id
  principal_id       = azurerm_container_app.demo[0].identity[0].principal_id
}

output "demo_url" {
  value = var.enable_app ? "https://${azurerm_container_app.demo[0].name}.${azurerm_container_app_environment.demo.default_domain}" : null
}

output "foundry_project_id" {
  value = azurerm_cognitive_account_project.demo.id
}

output "resource_group" {
  value = azurerm_resource_group.demo.name
}

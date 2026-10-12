# Foundry intent-routing demo

This is a **synthetic** demonstration of routing natural-language queries to a generative or deterministic path. It contains no imported FAQ text, documents, customer data, or proprietary policy. All sample identifiers and answers are fictional.

Microsoft-Decision-1 makes a typed `choice` decision through the Foundry `/providers/microsoft/v1/systemone` endpoint. If confident enough, the LLM branch uses GPT-4.1 mini with only the included fictional examples as context. The deterministic branch answers only exact synthetic matches and performs no transactions. Neither model generates a decision rationale; the displayed reason is the static description of the selected category. This is a demo, not a calibrated production classifier.

Foundry IQ is **not connected**: the bounded synthetic dataset does not need a search index. To use a real knowledge base, connect an authorized source to Foundry IQ, enforce source permissions, and replace the prompt context. Do not commit private knowledge content to this repo.

## Deployment

Prerequisites: Azure CLI signed into your target tenant/subscription, Terraform >= 1.6, permission to create Foundry resources and Entra app registrations, and Azure CLI `containerapp` support. Resource creation, registry storage/builds, and model calls can incur charges.

1. In `infra/`, create a local `local.auto.tfvars` (ignored by Git) with `subscription_id`, `tenant_id`, a unique `name_suffix`, and `enable_app = false`. Run `terraform init`, `terraform validate`, and `terraform apply`. This provisions the Foundry project, both model deployments, registry, environment, and restricted Entra app.
2. At the repo root build the image: `az acr build --registry <your-registry-name> --image intent-demo:v1 --file Dockerfile .`.
3. In `infra/local.auto.tfvars`, set `enable_app = true`, then `terraform apply`. This creates the app with **internal ingress**, managed-identity access to Foundry, and Entra authentication.
4. Check the auth config and restricted identity before opening ingress. Then set `enable_public_ingress = true` and run `terraform apply`. Output `demo_url` is the HTTPS URL. Anonymous requests must redirect to sign-in; only the assigned identity is authorized.

`local.auto.tfvars`, Terraform state/plan files, and build artifacts must never be committed: state contains an Entra client secret. Keep the local state protected. The demo uses a one-replica maximum and a 0.65 **illustrative** abstention threshold; calibrate it on representative labeled examples for production.

Tenants with user consent disabled require an Entra administrator to grant consent to this app's three sign-in-only OpenID scopes (`openid`, `profile`, `email`) before the assigned user can sign in. No Microsoft Graph data permissions are requested. The administrator can use the app registration's **API permissions > Grant admin consent** action; Azure subscription Owner rights alone do not grant Entra administrator consent.

Run local tests with `python -m unittest discover -s tests -v` after installing `requirements.txt` in a virtual environment. To retire the demo, remove the app safely and run `terraform destroy` from `infra/`; verify the plan before confirming deletion.

For a private runtime smoke test, run `az containerapp exec --name <app-name> --resource-group <group> --command "python smoke.py"` after deployment. It exercises both model-backed routes with only fictional inputs.

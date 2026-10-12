# Foundry intent-routing demo

This is a **synthetic** demonstration of routing natural-language queries to a generative or deterministic path. It contains no imported FAQ text, documents, customer data, or proprietary policy. All sample identifiers and answers are fictional.

Microsoft-Decision-1 makes a typed `choice` decision through the Foundry `/providers/microsoft/v1/systemone` endpoint. If confident enough, the LLM branch uses GPT-4.1 mini with only the included fictional examples as context. The deterministic branch answers only exact synthetic matches and performs no transactions. Neither model generates a decision rationale; the displayed reason is the static description of the selected category. This is a demo, not a calibrated production classifier.

Foundry IQ is **not connected**: the bounded synthetic dataset does not need a search index. To use a real knowledge base, connect an authorized source to Foundry IQ, enforce source permissions, and replace the prompt context.

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

## Troubleshooting

Start with the symptom, then check the app and the relevant identity or model. Use the resource names and app ID from **your own** Terraform outputs and Entra app registration; do not put tenant IDs, secrets, Terraform state, or private documents in an issue.

| Symptom | Check and resolution |
| --- | --- |
| **"Need admin approval" at sign-in** | The checkmark beside a greyed-out **Grant admin consent** button is an icon, **not** proof of consent. In **Entra ID > App registrations > this app > API permissions**, the **Status** column must say **Granted for \<tenant\>** for `openid`, `profile`, and `email`. A tenant administrator must grant consent if tenant policy blocks user consent; subscription Owner access does not suffice. Keep the app's assigned-user restriction in place. |
| **401 at `/.auth/login/aad/callback`** | First resolve any admin-consent prompt, then retry in an InPrivate window with the user assigned to the Enterprise application. Confirm the app registration's web redirect URI exactly matches `https://<app-host>/.auth/login/aad/callback`, **ID token issuance** is enabled (the auth flow requests `code+id_token`), and Container Apps auth references the correct client secret. Do not publish or paste the secret. |
| **401 on a command-line request to `/`** | This can be the expected response for a client that does not follow interactive sign-in. Open the URL in a browser; unauthenticated access must lead to Microsoft sign-in, **not** the demo UI. If it instead exposes the UI, disable public ingress until auth is fixed. |
| **403 after a successful sign-in** | Verify the user's object ID is assigned to the Enterprise application and matches the Container Apps auth `allowedPrincipals.identities` list. Sign in to the configured tenant, not a different cached account. |
| **Decision API 401/403** | Use the Foundry `https://<resource>.services.ai.azure.com/providers/microsoft/v1/systemone` endpoint, not the `.cognitiveservices.azure.com` endpoint. The caller's managed identity needs the `Microsoft.CognitiveServices/accounts/AIServices/providers/action` data action; the OpenAI User role alone does not include it. Allow time for a new role assignment to propagate. |
| **Model call 429** | Check the relevant deployment quota and rate limit. The Decision-1 and generative models have separate capacities in Terraform; adjust `sku.capacity` within available quota and reapply. Keep the error visible rather than inventing an answer. |
| **App unavailable, image pull error, or 502/503** | Check the ready revision, container and system logs, registry image tag, and the pull identity's `AcrPull` assignment. Ensure the container listens on port 8000. Scale-to-zero can cause a cold start; investigate logs before changing replica settings. |
| **Terraform 409 on Foundry resources** | Another operation on the same Foundry account may still be running. Wait for it to finish and re-run `terraform plan`/`terraform apply`; the model and project resources are deliberately sequenced. |
| **Model deployment name rejected** | Azure can reject reserved words in the *deployment name*. Use a neutral deployment name such as `intent-decision` while keeping the underlying model name `Microsoft-Decision-1`. |
| **App Service F1/B1 quota is zero** | This project uses a Container Apps consumption environment instead of an App Service plan. Do not switch hosts without checking regional quota and authentication behavior. |

Useful read-only checks (run in the target subscription):

```powershell
az ad app permission list-grants --id <app-client-id> -o json
az containerapp show --name <app-name> --resource-group <resource-group> --query "{status:properties.runningStatus,revision:properties.latestReadyRevisionName,ingress:properties.configuration.ingress}" -o json
az containerapp revision list --name <app-name> --resource-group <resource-group> -o table
az containerapp logs show --name <app-name> --resource-group <resource-group> --tail 50
az containerapp logs show --name <app-name> --resource-group <resource-group> --type system --tail 50
```

An empty grant list means no consent grant is visible to this query. If the portal still blocks sign-in after an administrator grants consent, inspect **Entra ID > Sign-in logs** for the specific error code and timestamp, then re-check the registration and allowed identity; do not remove authentication to bypass the error.

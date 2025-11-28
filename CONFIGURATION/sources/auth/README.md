# Authentication Examples

This directory contains complete, working examples for all supported authentication methods.

## Available Examples

### 1. [No Authentication](./no-auth.yaml)
**Use Case:** Public APIs that don't require authentication

**Example API:** JSONPlaceholder (free fake REST API)

**Key Features:**
- Simple instant scrape
- Delta detection with fingerprint keys
- Basic counter metrics and attributes

**Quick Start:**
```bash
# No credentials needed
uv run otel-api-scraper
```

---

### 2. [Basic Authentication](./basic-auth.yaml)
**Use Case:** APIs using HTTP Basic Auth (username/password)

**Key Features:**
- Username and password from environment variables
- Instant scrape with data nesting
- Gauge and counter metrics

**Quick Start:**
```bash
export API_USERNAME="your-username"
export API_PASSWORD="your-password"
uv run otel-api-scraper
```

---

### 3. [API Key Authentication](./apikey-auth.yaml)
**Use Case:** Most modern REST APIs (Stripe, SendGrid, etc.)

**Example API:** Stripe Charges API

**Key Features:**
- Custom header authentication
- Range-based scraping with time windows
- Histogram metrics for distributions
- Log severity mapping based on status
- Delta detection

**Quick Start:**
```bash
export STRIPE_API_KEY="sk_live_xxxxxxxxxxxxx"
uv run otel-api-scraper
```

---

### 4. [OAuth - Static Token](./oauth-static-token.yaml)
**Use Case:** APIs with long-lived OAuth tokens (GitHub, GitLab)

**Example API:** GitHub Issues API

**Key Features:**
- Pre-generated OAuth token from environment
- Nested data extraction (user.login)
- Delta detection with multiple keys

**Quick Start:**
```bash
export GITHUB_TOKEN="ghp_xxxxxxxxxxxxx"
uv run otel-api-scraper
```

**How to get a GitHub token:**
1. Go to GitHub Settings → Developer settings → Personal access tokens
2. Generate new token (classic) with `repo` scope
3. Copy the token and set as environment variable

---

### 5. [OAuth - Runtime Token Fetch](./oauth-runtime-token.yaml)
**Use Case:** OAuth2 Client Credentials flow

**Key Features:**
- Dynamic token acquisition before each scrape
- Client ID and secret authentication
- Custom token endpoint configuration
- Advanced filtering (drop/keep rules)
- Record limits per scrape
- Status-to-metric mapping

**Quick Start:**
```bash
export OAUTH_CLIENT_ID="your-client-id"
export OAUTH_CLIENT_SECRET="your-client-secret"
uv run otel-api-scraper
```

**How it works:**
1. Scraper calls token endpoint with client credentials
2. Token endpoint returns `{"access_token": "...", "expires_in": 3600}`
3. Access token is used for API requests
4. Token is refreshed automatically as needed

---

### 6. [Azure AD Authentication](./azuread-auth.yaml)
**Use Case:** Microsoft Azure APIs, Microsoft Graph, Microsoft 365

**Example APIs:**
- Azure Resource Manager (metrics)
- Microsoft Graph (users)

**Key Features:**
- Service principal authentication
- Azure-specific token endpoint
- Resource-based access control
- Multiple examples in one file

**Quick Start:**
```bash
export AZURE_CLIENT_ID="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
export AZURE_CLIENT_SECRET="your-client-secret"
# Update tokenEndpoint with your tenant ID in the config
uv run otel-api-scraper
```

**How to create a service principal:**
```bash
az ad sp create-for-rbac \
  --name "otel-scraper" \
  --role Reader \
  --scopes /subscriptions/{subscription-id}
```

---

## Choosing the Right Authentication Method

| API Provider | Recommended Auth Type | Example File |
|--------------|----------------------|--------------|
| Public APIs (no auth) | None | [no-auth.yaml](./no-auth.yaml) |
| Internal/Legacy APIs | Basic Auth | [basic-auth.yaml](./basic-auth.yaml) |
| Modern REST APIs | API Key | [apikey-auth.yaml](./apikey-auth.yaml) |
| GitHub, GitLab | OAuth (Static) | [oauth-static-token.yaml](./oauth-static-token.yaml) |
| SaaS APIs with OAuth2 | OAuth (Runtime) | [oauth-runtime-token.yaml](./oauth-runtime-token.yaml) |
| Azure, Microsoft 365 | Azure AD | [azuread-auth.yaml](./azuread-auth.yaml) |

## Using These Examples

### Copy and Modify
1. Choose the example that matches your API's auth method
2. Copy the file to your config directory
3. Update the values:
   - `baseUrl` and `endpoint`
   - Environment variable names
   - Data extraction paths (`dataKey`, metric fields)
   - Metric names and labels

### Merge with Existing Config
These examples show complete `sources` entries. To add to an existing config:

```yaml
# Your existing config.yaml
scraper:
  # ... global settings ...

sources:
  # Copy the source entry from the example
  - name: "my-api"
    baseUrl: "https://api.example.com"
    # ... rest from example ...
```

### Test First
1. Enable dry run mode to test without sending data:
   ```yaml
   scraper:
     dryRun: true
   ```

2. Run a single scrape:
   ```yaml
   sources:
     - name: "my-api"
       scrape:
         runFirstScrape: true
   ```

## Security Best Practices

✅ **DO:**
- Store credentials in environment variables
- Use secret management (AWS Secrets Manager, Azure Key Vault, etc.)
- Rotate API keys regularly
- Use least-privilege access (minimal scopes/permissions)
- Add `.env` to `.gitignore`

❌ **DON'T:**
- Hardcode credentials in config files
- Commit credentials to version control
- Share API keys in plain text
- Use production credentials in development

## Troubleshooting

### Authentication Fails
```
Error: 401 Unauthorized
```
- Verify environment variables are set correctly
- Check API key/token hasn't expired
- Ensure proper scopes/permissions are granted
- For Azure AD: verify tenant ID and resource URL

### Token Endpoint Errors (OAuth Runtime)
```
Error: Cannot fetch OAuth token
```
- Check `getTokenEndpoint` URL is correct
- Verify `tokenKey` matches the response field
- Inspect `bodyData` format (JSON vs form-encoded)
- Test the token endpoint manually with curl

### Azure AD Issues
```
Error: Invalid resource
```
- Ensure `resource` ends with `/` (e.g., `https://management.azure.com/`)
- Verify tenant ID in `tokenEndpoint`
- Check service principal has correct permissions

## Additional Resources

- [Main Configuration Docs](../../README.md)
- [Source Configuration Reference](../README.md)
- [Global Configuration Reference](../../global/README.md)
- [config.yaml.template](../../../config.yaml.template)

## Contributing

Found a useful authentication pattern not covered here? Please contribute!

1. Create a new example file following the existing format
2. Add comprehensive comments
3. Include environment variable documentation
4. Update this README with your example


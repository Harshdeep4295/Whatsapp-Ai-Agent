# Workload Identity Federation Setup (No Static Keys!)

This setup uses GitHub OIDC tokens instead of static service account keys - more secure and aligns with security best practices.

---

## Step 1: Set Up Workload Identity Pool & Provider

```bash
PROJECT_ID=$(gcloud config get-value project)
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')

echo "Project ID: $PROJECT_ID"
echo "Project Number: $PROJECT_NUMBER"

# Enable required APIs
gcloud services enable iamcredentials.googleapis.com
gcloud services enable cloudresourcemanager.googleapis.com
gcloud services enable sts.googleapis.com

# Create Workload Identity Pool
gcloud iam workload-identity-pools create "github" \
  --project=$PROJECT_ID \
  --location="global" \
  --display-name="GitHub"

# Create Workload Identity Provider (for GitHub)
gcloud iam workload-identity-pools providers create-oidc "github" \
  --project=$PROJECT_ID \
  --location="global" \
  --workload-identity-pool="github" \
  --display-name="GitHub Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.aud=assertion.aud,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-condition="assertion.repository_owner == 'YOUR_GITHUB_USERNAME'"
```

**Replace `YOUR_GITHUB_USERNAME`** with your actual GitHub username!

---

## Step 2: Grant GitHub Permission to Impersonate Service Account

```bash
PROJECT_ID=$(gcloud config get-value project)
GITHUB_REPO="YOUR_GITHUB_USERNAME/whatsapp-agent"

# Get the Workload Identity Provider resource name
WIF_PROVIDER=$(gcloud iam workload-identity-pools providers describe github \
  --workload-identity-pool=github \
  --location=global \
  --project=$PROJECT_ID \
  --format='value(name)')

echo "WIF Provider: $WIF_PROVIDER"

# Allow GitHub to impersonate the service account
gcloud iam service-accounts add-iam-policy-binding \
  github-deployer@$PROJECT_ID.iam.gserviceaccount.com \
  --project=$PROJECT_ID \
  --role="roles/iam.workloadIdentityUser" \
  --principal="principalSet://iam.googleapis.com/$WIF_PROVIDER/attribute.repository/$GITHUB_REPO"
```

**Replace `YOUR_GITHUB_USERNAME/whatsapp-agent`** with your repo path!

---

## Step 3: Get Values for GitHub Secrets

```bash
PROJECT_ID=$(gcloud config get-value project)
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')

# Get Workload Identity Provider resource name
WIF_PROVIDER=$(gcloud iam workload-identity-pools providers describe github \
  --workload-identity-pool=github \
  --location=global \
  --project=$PROJECT_ID \
  --format='value(name)')

echo "=== Add these to GitHub Secrets ==="
echo ""
echo "GCP_PROJECT_ID: $PROJECT_ID"
echo ""
echo "GCP_WORKLOAD_IDENTITY_PROVIDER: $WIF_PROVIDER"
echo ""
echo "GCP_SERVICE_ACCOUNT_EMAIL: github-deployer@$PROJECT_ID.iam.gserviceaccount.com"
echo ""
```

Copy these values! You'll need them for GitHub.

---

## Step 4: Add GitHub Secrets

1. Go to your GitHub repo → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret** and add:

| Secret Name | Value |
|---|---|
| `GCP_PROJECT_ID` | Your Project ID |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | From Step 3 output |
| `GCP_SERVICE_ACCOUNT_EMAIL` | `github-deployer@PROJECT_ID.iam.gserviceaccount.com` |
| `WHATSAPP_TOKEN` | Your WhatsApp token |
| `WHATSAPP_VERIFY_TOKEN` | Your verify token |
| `SUPABASE_URL` | Your Supabase URL |
| `SUPABASE_KEY` | Your Supabase key |
| `GROQ_API_KEY` | Your Groq API key |
| `OPENAI_API_KEY` | Your OpenAI API key |
| `ADMIN_CHAT_ID` | Your admin chat ID |

---

## Step 5: Delete Old Workflow & Use New One

```bash
# Delete the old workflow file
rm .github/workflows/deploy.yml

# The new one is already there: deploy-wif.yml
```

---

## Step 6: Commit and Deploy

```bash
git add .github/workflows/deploy-wif.yml WIF_SETUP.md
git commit -m "Switch to Workload Identity Federation for secure deployment"
git push origin main
```

GitHub Actions will now:
✅ Request a token from GitHub OIDC provider
✅ Exchange it with Google Cloud (no static keys!)
✅ Deploy to Cloud Run
✅ Token expires after workflow finishes

---

## Verify Deployment

1. Go to GitHub repo → **Actions** tab
2. Watch the "Deploy to Cloud Run" workflow
3. Check logs for deployment URL
4. Update Meta webhook with new URL

---

## Troubleshooting

### "Invalid workload identity provider"
- Make sure you copied the `GCP_WORKLOAD_IDENTITY_PROVIDER` correctly
- Run Step 3 again and copy the exact output

### "Permission denied"
- Check that the service account permissions were granted in Step 2
- Verify your GitHub username in the attribute condition (Step 1)

### Check what permissions are set:
```bash
PROJECT_ID=$(gcloud config get-value project)
gcloud iam service-accounts get-iam-policy \
  github-deployer@$PROJECT_ID.iam.gserviceaccount.com
```

---

## Advantages of WIF:
✅ No static keys to manage
✅ Automatic token rotation
✅ Token expires after workflow finishes
✅ Better security posture
✅ Free to use

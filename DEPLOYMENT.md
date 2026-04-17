# GitHub Actions + Google Cloud Run Deployment Setup

## Step 1: Create a Google Cloud Service Account

### 1.1 Create Service Account
```bash
gcloud iam service-accounts create github-deployer \
  --display-name="GitHub Deployer"
```

### 1.2 Grant permissions to service account
```bash
# Get your project ID
PROJECT_ID=$(gcloud config get-value project)

# Grant Cloud Run Admin permission
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:github-deployer@$PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/run.admin

# Grant Service Account User permission
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:github-deployer@$PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/iam.serviceAccountUser

# Grant Container Registry push permission
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:github-deployer@$PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/storage.admin
```

### 1.3 Create and download Service Account Key
```bash
PROJECT_ID=$(gcloud config get-value project)

gcloud iam service-accounts keys create key.json \
  --iam-account=github-deployer@$PROJECT_ID.iam.gserviceaccount.com

# The key.json file is created. You'll use this in Step 2.
```

---

## Step 2: Add GitHub Secrets

Go to your GitHub repository:
1. Settings → Secrets and variables → Actions
2. Click "New repository secret" and add these:

| Secret Name | Value |
|---|---|
| `GCP_PROJECT_ID` | Your Google Cloud Project ID (from `gcloud config get-value project`) |
| `GCP_SA_KEY` | Contents of `key.json` (the entire file as text) |
| `WHATSAPP_TOKEN` | Your WhatsApp Business API token |
| `WHATSAPP_VERIFY_TOKEN` | Your webhook verify token |
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_KEY` | Your Supabase API key |
| `GROQ_API_KEY` | Your Groq API key |
| `OPENAI_API_KEY` | Your OpenAI API key |
| `ADMIN_CHAT_ID` | Your admin chat ID |

---

## Step 3: Commit and Push

```bash
git add .github/workflows/deploy.yml Dockerfile .gcloudignore
git commit -m "Add Cloud Run deployment workflow"
git push origin main
```

---

## Step 4: Watch Deployment

1. Go to your GitHub repo → Actions tab
2. You'll see "Deploy to Cloud Run" workflow running
3. Wait for it to complete (usually 2-3 minutes)
4. Once done, it will show your Cloud Run URL

---

## Step 5: Update Meta Webhook

After successful deployment:
1. Get the new URL from Actions output or:
   ```bash
   gcloud run services describe whatsapp-agent --platform managed --region us-central1 --format='value(status.url)'
   ```

2. Update Meta WhatsApp Configuration:
   - Webhook URL: `https://whatsapp-agent-xxx.run.app/webhook`
   - Verify Token: (same as before)

---

## Automatic Deployments

Now every time you push to `main`:
✅ GitHub Actions automatically builds & deploys to Cloud Run
✅ No manual deployment needed
✅ New URL is shown in Actions logs (if it changes)

---

## Troubleshooting

### Check deployment logs:
```bash
gcloud run logs read whatsapp-agent --follow
```

### Check GitHub Actions logs:
- Go to GitHub repo → Actions → Click the failed workflow → See error details

### Common Issues:
- **"Permission denied"**: Check GCP_SA_KEY secret is set correctly
- **"Build failed"**: Check requirements.txt has all dependencies
- **"Timeout"**: Increase timeout in workflow file

---

## Manual Deployment (if needed):
```bash
gcloud run deploy whatsapp-agent \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

# AURUM OS

AI-native gold trading copilot for disciplined discretionary execution.

## Project Structure

- `/web` - Next.js (App Router) Frontend
- `/api` - Python FastAPI Backend

## Local Development

### Prerequisites
- Node.js 18+
- Python 3.11+
- Postgres (Neon)

### Setup

1. **Clone the repository**
   \`\`\`bash
   git clone <repo-url>
   cd aurum-os
   \`\`\`

2. **Environment Variables**
   Copy `.env.example` to `.env` in the root folder and fill in the required values (Clerk, Database).

3. **Backend Setup (FastAPI)**
   \`\`\`bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   \`\`\`
   Start the FastAPI server:
   \`\`\`bash
   uvicorn api.index:app --reload --port 8000
   \`\`\`
   API runs at `http://localhost:8000`.

4. **Frontend Setup (Next.js)**
   \`\`\`bash
   cd web
   npm install
   \`\`\`
   Start the Next.js app:
   \`\`\`bash
   npm run dev
   \`\`\`
   Web app runs at `http://localhost:3000`.

## GitHub to Vercel Deployment

This repository is structured for native deployment to Vercel via GitHub connection.

1. **Push to GitHub**
   Commit all changes and push this repository to GitHub.

2. **Import to Vercel**
   - In Vercel, click "Add New..." -> "Project".
   - Select this GitHub repository.
   - **Important Configuration during import:**
     - **Framework Preset:** Leave it as Next.js or Auto. Our `vercel.json` will override the build map.
     - **Root Directory:** Leave empty (`/`). The `vercel.json` file handles routing to `/web` and `/api`.
   - Configure Environment Variables based on `.env.example`.

3. **Deploy**
   - Click Deploy. Vercel will build the `web` folder and deploy the `/api` Serverless Functions.
   - All PRs will generate automatic preview deployments.

### Production scout (human approval)

`vercel.json` schedules `GET /api/cron/scout` every 15 minutes. The handler writes each recommendation as a TradeIdea with status `Ready for Approval`. Open **Approvals** (`/app/approvals`), choose **Sign & Approve** (this stores an `ApprovalEvent`), then **Send to Execution Matrix**. That Execute click is the broker write.

Set these on the Vercel project. Keep the secret out of git:

- `AURUM_AGENTS_ENABLED=true` — `false` makes the cron return without staging
- `AURUM_AUTO_APPROVE=0` — ideas stay in the approval queue
- `CRON_SECRET` — a random string. Vercel sends it as `Authorization: Bearer …`, and the route checks it

A 15-minute cron needs Vercel Pro. Hobby accounts reject any schedule that runs more than once a day, and that rejection blocks the deployment. `/api/cron/hunt` is intentionally unscheduled: that route places market sells. Exits use the same Approvals Execute step.

## Architecture Guidelines

- All backend changes mapping to database schemas must use Alembic migrations.
- UI elements prefer `shadcn/ui` using the dark-mode primary configuration.
- The execution layer must always validate an \`ApprovalEvent\` before triggering broker adapters.

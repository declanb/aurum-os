# Helm

AI-native crypto trading copilot for disciplined, human-in-the-loop execution on Revolut X (spot only).

The product name is **Helm**. This repository is `aurum-os`. Package paths, env prefixes (`AURUM_*`), and internal identifiers stay Aurum unless a string is product branding.

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

## Architecture Guidelines

- All backend changes mapping to database schemas must use Alembic migrations.
- UI elements prefer `shadcn/ui` using the dark-mode primary configuration.
- The execution layer must always validate an \`ApprovalEvent\` before triggering broker adapters. Helm is wired to a live Revolut X account (real funds). Agents may recommend and stage a \`TradeIdea\` only. Path: TradeIdea → Approvals UI → human execute click → broker. Auto-approve is not auto-execute. Spot only — no shorts, leverage, or perps.
- Revolut X spot cannot attach a stop or target. Helm exit brackets own those sells. See `docs/helm-exit-brackets.md`.
- The paper copy book (`/app/copy`, `POST /api/copy/session`) simulates scout ideas and EUR gainers on a virtual balance. Default bankroll is €200 (`HELM_COPY_BANKROLL_EUR`). Revolut X has no copy API. That path never places a live order. See `docs/helm-copy-book.md`.
- Helm trades a symmetric +3% / −3% bracket (net of fees) on at most two scout ideas a day. See `docs/helm-strategy.md`.

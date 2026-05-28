# V3_Bot — Deployment Guide

## Live Environment
- **Droplet IP:** `167.172.137.169`
- **Backend:** FastAPI on port 8000 (proxied by nginx on port 80)
- **Bot:** discord.py on port 8001 (internal only)
- **Frontend:** Currently Jinja HTML → being replaced with React build

---

## Deploying the React Frontend

### 1. Build
```bash
cd C:\Users\ebwes\V3_Bot\frontend
npm run build
```
This creates `frontend/dist/`.

### 2. Upload to droplet
```bash
scp -r dist/* root@167.172.137.169:/var/www/v3bot/
```
(Adjust path to wherever nginx serves static files from)

### 3. Update nginx config
```nginx
server {
    listen 80;

    # React static files
    root /var/www/v3bot;
    index index.html;

    # API routes proxy to FastAPI
    location ~ ^/(api|ui|shows|bin|vouchers|trade|inventory|claims|users|media|health|watcher) {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # React Router catch-all — must come AFTER API routes
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

### 4. Reload nginx
```bash
sudo nginx -s reload
```

---

## Deploying Backend Changes

### Via Git
```bash
# Local — commit and push
git add Backend/routes/ui.py Core/bin_queue.py  # (whichever files changed)
git commit -m "description"
git push origin react-frontend

# On droplet — pull and restart
ssh root@167.172.137.169
cd /path/to/V3_Bot
git pull origin react-frontend   # or main if merged
sudo systemctl restart v3bot-backend  # or however the process is managed
```

---

## Local Dev — Testing Against Live Droplet

Use the Vite proxy so API calls hit the live backend:

```js
// vite.config.js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api':       'http://167.172.137.169',
      '/ui':        'http://167.172.137.169',
      '/shows':     'http://167.172.137.169',
      '/bin':       'http://167.172.137.169',
      '/vouchers':  'http://167.172.137.169',
      '/trade':     'http://167.172.137.169',
      '/inventory': 'http://167.172.137.169',
      '/claims':    'http://167.172.137.169',
      '/users':     'http://167.172.137.169',
      '/media':     'http://167.172.137.169',
      '/health':    'http://167.172.137.169',
      '/watcher':   'http://167.172.137.169',
    }
  }
})
```

Then: `npm run dev` → open `http://localhost:5173`

---

## Git Branch Strategy
- `main` — what the droplet runs
- `react-frontend` — active development branch
- Merge `react-frontend` → `main` when ready to deploy

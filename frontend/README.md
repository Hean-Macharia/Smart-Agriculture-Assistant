# ShambaLink Frontend

React + Vite frontend for the Smart Agricultural Advisory and Market Linkage System.

## Run locally

From the backend directory, the single-command launcher activates `venv`, builds the frontend if the build is absent, starts FastAPI, and opens the site in your browser:

    .\start.ps1

Stop the server with Ctrl+C. If PowerShell blocks local scripts, run `Set-ExecutionPolicy -Scope Process Bypass` in that terminal, then retry.

For separate development servers, open two PowerShell terminals.

Terminal 1, from the backend directory:

    .\venv\Scripts\Activate.ps1
    uvicorn app.main:app --reload

Terminal 2, from frontend:

    npm install
    npm run dev

Vite opens http://127.0.0.1:5173 automatically and proxies every backend route plus `/openapi.json` to http://127.0.0.1:8000. Copy .env.example to .env only if you need a different local backend target.

## Production build

    npm run build

The build is written to frontend/dist. The FastAPI app serves that folder at / when it exists, while preserving API routes. Include a frontend build step in the Render build command before starting Uvicorn, for example:

    pip install -r requirements.txt && npm --prefix frontend install && npm --prefix frontend run build

If deploying the backend and frontend on separate domains, set VITE_API_BASE_URL to the backend origin and add the frontend origin to the backend CORS_ALLOWED_ORIGINS setting.

## Connected features

- Public produce browsing and county/category/search filters use GET /marketplace/products.
- Account registration and sign-in use /auth/register/{farmer,buyer}, /auth/login, and /auth/me.
- Farmer workspace uses farms, crops, listings, seller orders, and weather recommendations.
- Buyer workspace places orders and initiates payments.
- In development with PAYMENT_PROVIDER=mock, the payment panel may call the backend mock callback. It labels the result as simulated and never claims it is a real M-Pesa transaction.
- Weather and disease screening show provider/model errors returned by the backend; the interface does not invent forecast or diagnosis results.
- Market prices are explicitly labeled as recorded observations.

The decorative Three.js field scene is lightweight and respects prefers-reduced-motion; critical controls remain usable without WebGL. Forms use the backend request fields. Live M-Pesa, weather, SMS, or disease screening require their backend provider credentials or model assets.


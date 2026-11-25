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

## Install ShambaLink on a phone

The production build is an installable Progressive Web App (PWA). Serve it over HTTPS in production; service workers are not available on ordinary insecure remote origins. On Android, open the deployed site in a supported browser such as Chrome and choose **Install app** or **Add to Home screen** from the browser menu. On iPhone, open the deployed site in Safari, tap **Share**, choose **Add to Home Screen**, confirm the name, then launch ShambaLink from the home screen. The app has a web manifest, Apple web-app metadata, and touch icons.

The repository's browser automation tests the production build in Chromium, including an actual browser offline navigation. That is not a physical Android or iPhone test. iOS may evict site storage and restrict background execution; this application therefore syncs while it is open, when it regains focus/connectivity, or when the farmer taps **Sync now**. It does not depend on Background Sync or claim background delivery. Test the installed experience on the target iOS/Android versions before a field rollout.

## Offline behavior and data boundaries

- The service worker caches only the application shell and built static assets. It deliberately does not cache API responses. If an API is unavailable, the UI uses farmer-scoped IndexedDB snapshots and labels cached weather as potentially outdated.
- IndexedDB stores downloaded farm/crop and other supported snapshots, a per-account pending farm/crop operation queue, and private marketplace listing drafts. Farm and crop create requests sync with a stable idempotency key. Crop edits use `If-Match`; if the server version changed, the app keeps the local edit and asks the farmer to choose whether to apply it over the latest server version.
- Pending changes are scoped by authenticated account ID. After a browser restart the JWT is not restored from persistent storage; the farmer must sign in again before queued changes can sync. Local records are device/browser data, not an encrypted backup; use a device lock and do not share a browser profile. Clearing browser storage or iOS evicting site data can remove unsynced records.
- A saved listing is a local draft and is not visible to buyers until submitted online. Orders, stock reservation, payments, delivery updates, live weather requests, SMS provider communication, and disease-model prediction require the backend/network. The interface does not report those as completed offline.
- Disease inference remains server-side; no TensorFlow Lite/JavaScript model is included. Push notifications are not configured. The existing USSD feature remains a development simulator unless a carrier gateway and short code are provisioned.

## PWA and offline verification

From `frontend`, run:

    npm run test:pwa

This builds the production app and runs Playwright checks for manifest metadata, service-worker-controlled offline navigation, API non-caching, and persistence/synchronization of a farm created offline. The API is mocked in the workflow test, so that test is not evidence of live MongoDB persistence. The backend uses idempotency keys to make retried farm/crop creates safe; it does not claim that a browser-only test proves an external deployment.

For a phone demonstration, sign in while online and open the required pages once so their supported records are saved locally. Switch on airplane mode, reopen the installed app, inspect the Offline and last-sync indicators, add a farm/crop or listing draft, close and reopen the app, then reconnect and sign into the same account before syncing. Verify successful records in the backend only after the app reports synchronization complete. Do not try payment, SMS, or real order workflows in airplane mode.

## Connected features

- Public produce browsing and county/category/search filters use GET /marketplace/products.
- Account registration and sign-in use /auth/register/{farmer,buyer}, /auth/login, and /auth/me.
- Farmer workspace uses farms, crops, listings, seller orders, and weather recommendations.
- Buyer workspace places orders and initiates payments.
- In development with PAYMENT_PROVIDER=mock, the payment panel may call the backend mock callback. It labels the result as simulated and never claims it is a real M-Pesa transaction.
- Weather and disease screening show provider/model errors returned by the backend; the interface does not invent forecast or diagnosis results.
- Market prices are explicitly labeled as recorded observations.

The decorative Three.js field scene is lightweight and respects prefers-reduced-motion; critical controls remain usable without WebGL. Forms use the backend request fields. Live M-Pesa, weather, SMS, or disease screening require their backend provider credentials or model assets.


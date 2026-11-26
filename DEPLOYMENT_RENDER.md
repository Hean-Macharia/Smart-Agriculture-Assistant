# Render production deployment

This repository now includes a Docker-based Render Blueprint template. Its deliberately distinct service name avoids matching the currently deployed service by name; applying it creates a separate service. It builds the React/Vite frontend and serves it from the FastAPI app on the same origin, so the production frontend does not need a separate CORS origin.

## Before connecting the Blueprint

The Blueprint is a template. Review the service name and environment values in `render.yaml` before applying it. Automatic deploys are disabled. Do not attach it to or sync it with an existing production service until you have compared the Blueprint values with that service's environment. In particular, changing `JWT_SECRET_KEY` invalidates existing access tokens.

The default payment, escrow, and SMS adapters are deliberately `mock`; this prevents a first deployment from initiating real payments or SMS. No real M-Pesa transaction or SMS is sent by the build or startup process. Safaricom Daraja production activation requires a deliberate environment change and all validated production credentials/callback settings. The app's internal escrow workflow is not regulated custody.

## Render setup

1. Push the reviewed project branch to the connected Git repository.
2. In Render, create a new Blueprint instance from that repository, or copy these settings into the existing Web Service after comparing its current configuration.
3. Use the Docker runtime and the repository root as the service root.
4. Set the required secret `MONGODB_URI` in the Render dashboard. Set `DATABASE_NAME` to the existing application database. Do not put either value in Git or share it in chat.
5. Preserve an existing production `JWT_SECRET_KEY` when updating the current service. For a new service, Render can generate one through the Blueprint. Do not regenerate it after users have active tokens unless you intend to log them out.
6. Keep `PAYMENT_PROVIDER=mock`, `ESCROW_PROVIDER=mock`, `SMS_PROVIDER=mock`, and `SMS_AUTO_DISPATCH=false` for the initial deploy. Configure credentials only in Render's secret environment settings and only enable a live provider after its callback/receipt workflow has been verified.
7. Deploy manually, then check both `https://<service>.onrender.com/health` and `/health/ready`. Render uses `/health` as a liveness check; `/health/ready` must report MongoDB connected before database-backed workflows are considered ready.
8. Open `/docs` and test non-financial workflows with dedicated test accounts. Do not use mock callbacks as evidence of real provider settlement.

## Production environment

Required values:

| Variable | Production value / handling |
| --- | --- |
| `APP_ENV` | `production` |
| `DEBUG` | `false` |
| `JWT_SECRET_KEY` | Secret, at least 32 characters; preserve it on an existing deployment |
| `MONGODB_URI` | Secret Atlas connection URI; database user needs least-privilege access to the app database |
| `DATABASE_NAME` | Existing application database name |
| `PAYMENT_PROVIDER` | Start with `mock`; choose `daraja` only after explicit production payment activation |
| `MPESA_ENVIRONMENT` | `sandbox` with mock provider; `production` only with explicitly configured production Daraja |
| `ESCROW_PROVIDER` | `mock` unless a real safeguarded-funds partner adapter is implemented and contracted |
| `SMS_PROVIDER` | `mock` until production sender, credentials, consent, and delivery receipts are configured |
| `SMS_AUTO_DISPATCH` | `false` until real outbound SMS delivery has been verified and authorized |
| `WEATHER_API_KEY` | Optional secret for the configured live weather provider |
| `DISEASE_MODEL_PATH`, `DISEASE_LABELS_PATH` | Set only when the matching model and labels are provisioned at durable paths |

In production, configuration validation rejects `DEBUG=true`, a missing/short JWT signing key, missing Mongo settings, and non-HTTPS or wildcard CORS origins. Since the React app and API share one origin, leave `CORS_ALLOWED_ORIGINS` empty unless you intentionally host a separate trusted frontend.

## Data durability and feature limitations

MongoDB remains the durable store for application records. Render's default service filesystem is ephemeral. The repository excludes trained disease-model assets from Git and production product-image uploads intentionally return 503 until durable object storage is configured. Do not store production uploads or model artifacts only in the container filesystem. Configure an appropriate object-storage integration or a Render persistent disk before enabling those features; a persistent disk requires a paid Render web service and constrains scaling/deploy behavior. Model predictions also require the TensorFlow runtime and matching `.keras`/labels files; this Docker image intentionally does not install the large optional `requirements-ml.txt` dependency.

The app's readiness endpoint verifies MongoDB only. A 200 response does not prove that M-Pesa, SMS, weather, model inference, or durable image storage is configured. Free Render instances can spin down when idle and have ephemeral filesystems, so select a service plan and persistence strategy appropriate to your availability needs.

## Build and runtime commands

The Blueprint uses the Dockerfile. For reference, the container builds with `npm ci` and `npm run build` in the frontend stage, installs `requirements.txt` in the Python stage, and starts with:

```sh
uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
```

For local pre-deploy checks from `backend/`:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest -q
python -m compileall -q app tests
npm --prefix frontend ci
npm --prefix frontend test
npm --prefix frontend run build
```

Do not run a production payment, send a real SMS, mutate production records, or attach paid storage as part of these checks.

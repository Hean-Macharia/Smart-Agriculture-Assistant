# Smart Agriculture Advisory and Market Linkage API

This FastAPI backend is being built in phases. Core features through Phase 14 are implemented, including configuration and health, JWT authentication and role checks, farmer/buyer profiles, farms and crops, marketplace listings and stock-reserving orders, payment adapters, verified Daraja callbacks, internal escrow workflow, an append-only transaction ledger, delivery tracking, disputes, weather forecasts, market price records/history, SMS adapters, model-backed crop image screening and monitoring, source-linked crop/pest education, and farmer/officer frontend views. External provider availability and live database readiness must still be checked in the target environment; see the verification notes below. A trained disease model and matching label file are required for inference.

## Requirements and installation

- Python 3.11 or later
- MongoDB reachable from the backend (local MongoDB or MongoDB Atlas)

From this `backend` directory in Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

If `.env` already exists, keep it and add the settings listed below instead of overwriting it. Set `MONGODB_URI` and `DATABASE_NAME`. For Atlas, use the current cluster URI with an empty database path and `authSource=admin` for a standard Atlas database user; grant that database user `readWrite` on `DATABASE_NAME`. `MONGODB_SERVER_SELECTION_TIMEOUT_MS` defaults to 15000 ms (valid range 1000–60000) to allow SRV discovery, TLS and replica-set server selection on slower networks; only set a deployment override if needed. Set `JWT_SECRET_KEY` and `ADMIN_BOOTSTRAP_TOKEN` to separate random values of at least 32 characters. In production set `APP_ENV=production` and `DEBUG=false`. Browser frontends must set `CORS_ALLOWED_ORIGINS` to a comma-separated list of exact origins; it defaults to empty. Do not commit `.env` or paste its secrets into shared Postman environments. No default administrator password is embedded in the application.

### Disease model setup

The endpoints are `POST /disease-detection/predict` (farmer JWT, multipart form field `image`), `GET /disease-detection/mine` (farmer JWT), and the public read-only `GET /disease-detection/knowledge` plus `GET /disease-detection/knowledge/{model_label}`. Upload JPEG, PNG, or WebP up to `DISEASE_IMAGE_MAX_BYTES` (8 MiB by default). The service decodes with Pillow, converts to RGB, resizes to `DISEASE_INPUT_SIZE` (224 by default), and scales pixels to 0–1. It stores prediction metadata and the image SHA-256 in MongoDB, not the original image. Prediction output is preliminary screening, not a diagnosis.

The knowledge catalogue provides general, non-chemical educational guidance for the 11 supported model labels, with source organization, title, URL, and reference location. `SOURCE_CHECKED` means the cited source was checked; it does not mean the content has been approved for a particular farm by a county extension officer. No pesticide/product recommendations are returned. Keep the warning and source links visible. Postman requests are in **Disease Detection > List source-backed disease guidance**, **Filter disease guidance by crop**, and **Get guidance for a model label**.

Install TensorFlow when a trained model is available: `python -m pip install -r requirements-ml.txt`. Configure `DISEASE_MODEL_PATH` and `DISEASE_LABELS_PATH` to a trusted Keras `.keras` model and a JSON list in output-index order (or `{"classes": [...]}`). Relative paths are resolved from the backend project root. The model must accept `(1, 224, 224, 3)` and output one score per label. Local `uploads/models/` assets are excluded from Git; supply them through an approved deployment asset/disk strategy and configure absolute paths in production. The local smoke check verifies loading and inference only; it does not establish field accuracy. Without model assets or TensorFlow, inference returns HTTP 503 rather than a fabricated prediction. TensorFlow is optional because it is a large runtime; see the [TensorFlow installation guide](https://www.tensorflow.org/install/pip).

For local MongoDB, defaults are `mongodb://localhost:27017` and database `smart_agriculture`. The API starts for diagnosis if MongoDB is down, but database-backed registration and login return unavailable until MongoDB responds.

## Run the API

To activate `venv`, start the backend, and open the built frontend automatically:

```powershell
.\start.ps1
```

The launcher builds `frontend/dist` first if it is missing. That first build requires Node.js/npm. Once built, the frontend is served from the same origin as the API at http://127.0.0.1:8000. `Ctrl+C` stops the server.

For backend-only development, use:

```powershell
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

- Swagger UI: http://127.0.0.1:8000/docs
- OpenAPI JSON: http://127.0.0.1:8000/openapi.json
- Liveness: http://127.0.0.1:8000/health
- MongoDB readiness: http://127.0.0.1:8000/health/ready

`GET /health` reports whether the API process responds. `/health/ready` performs a MongoDB ping and returns 200 only when MongoDB is reachable; otherwise it returns 503.

## Phase 2 authentication API

Authenticated requests use `Authorization: Bearer <access_token>`. Request and response schemas are shown in Swagger.

| Method | Endpoint | Access | Success |
|---|---|---|---|
| POST | `/auth/register/farmer` | Public | 201, farmer public profile |
| POST | `/auth/register/buyer` | Public | 201, buyer public profile |
| POST | `/auth/bootstrap-admin` | One-time server-token setup | 201, admin profile; 409 after an admin exists |
| POST | `/auth/login` | Public | 200, JWT and public profile |
| GET | `/auth/me` | Any authenticated user | 200, own public profile |
| PATCH | `/auth/me` | Any authenticated user | 200, updated own profile |
| POST | `/auth/admin/users` | ADMIN | 201, admin/officer profile |
| GET | `/auth/admin/users` | ADMIN | 200, paginated user profiles |

Registration accepts `full_name`, `email`, `phone`, and `password`. Emails are normalized to lowercase and Kenyan mobile numbers to `+254…`. Passwords are stored as Argon2 hashes. Public registration fixes the role server-side; an extra `role` field is rejected. Login accepts email and password. The token response includes `access_token`, `token_type`, `expires_in`, and an allowlisted user profile. A profile patch accepts `full_name` and/or `phone`.

The first administrator is provisioned once via `POST /auth/bootstrap-admin`, with `X-Admin-Bootstrap-Token` matching the private `ADMIN_BOOTSTRAP_TOKEN` configured on the server. Bootstrap is disabled when the token is missing/too short and rejects subsequent setup after an administrator exists. Sign in as that administrator to create further admins or agricultural officers. Admin creation is not public. Role-protected requests return 401 when unauthenticated and 403 for authenticated users without the required role. Duplicate email/phone returns 409; invalid input returns 422.

## Postman

Import `postman/Smart_Agriculture_API.postman_collection.json` and `postman/Smart_Agriculture_Environment.postman_environment.json`, then select **Smart Agriculture Local**. Set the environment's `admin_bootstrap_token` locally to match the server `.env`; never commit or share that value. Sample test credentials are for local development only. Change them before using a shared database. Login requests save `access_token`; buyer login also saves `buyer_access_token`. Registration saves farmer/buyer IDs.

Suggested Phase 2 run order:

1. Run Health > Liveness and MongoDB readiness. Resolve MongoDB readiness before account requests.
2. Send Authentication > Register farmer and Register buyer (201; on rerun, 409 is expected).
3. Set `admin_bootstrap_token` privately and send Bootstrap first admin once (201; rerun returns 409).
4. Send Login admin, then Admin creates agricultural officer and List users.
5. Send Login farmer, Current user, and Update my profile.
6. Send Login buyer and Buyer forbidden from admin user list (expected 403).
7. Run invalid login, missing token, and role-injection negative requests (401/422 expected).

Phase 2 invokes no M-Pesa, weather, SMS or escrow provider. Health readiness checks the configured MongoDB server. Auth pytest tests use an in-memory repository and never touch any database.

## Tests

From this directory, with the project virtual environment active:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest -q
```

HTTP tests use FastAPI's HTTPX-backed TestClient and isolated in-memory repositories. They cover auth and RBAC, farmer/buyer profiles, farm/crop ownership and validation, marketplace filters, concurrent stock reservation, cancellation/restock idempotency, order permissions, and invalid state transitions. Tests never use configured MongoDB.

## Phase 3 farmer, buyer, farm and crop APIs

| Method | Endpoint | Access | Purpose |
|---|---|---|---|
| PUT / GET | `/farmers/me` | FARMER | Create/update or read own farmer profile |
| PUT / GET | `/buyers/me` | BUYER | Create/update or read own buyer profile |
| POST | `/farms` | FARMER | Register an owned farm |
| GET | `/farms?limit=20&offset=0` | FARMER | List active farms owned by current user |
| GET / PATCH / DELETE | `/farms/{farm_id}` | FARMER owner | Read, update, or deactivate own farm |
| POST | `/crops` | FARMER | Record crop on an owned active farm |
| GET | `/crops?farm_id={id}&limit=20&offset=0` | FARMER | List own active crops, optionally by farm |
| GET / PATCH / DELETE | `/crops/{crop_id}` | FARMER owner | Read, update, or deactivate own crop |

Farmer profile fields include county, sub-county, location, farm size in acres, soil type, irrigation availability and crops grown. Buyer profile records county, sub-county, delivery location and optional organization name. User name, phone and email stay in the shared user account. Profiles are upserted per user.

Farm and crop ownership is taken from the authenticated account, never from request data. Attempting to access another user's farm/crop returns 404 to avoid disclosing whether it exists. Buyer/officer/admin roles cannot create farmer-only records. Deletion is a soft deactivation, preserving the record. Crop dates use ISO `YYYY-MM-DD`; harvest cannot be earlier than planting. Invalid values return 422. Lists are paginated (limit max 100).

### Postman Phase 3 workflow

1. Run Health and confirm MongoDB readiness is 200.
2. Register farmer and buyer if needed, then Login farmer. Login saves its token as `access_token`.
3. Run Farmers > Upsert my farmer profile.
4. Run Farms > Create farm, then List my farms, Get created farm, and Update farm. Creation saves `farm_id`.
5. Run Crops > Create crop, then List crops in farm, Get created crop, and Update crop. Creation saves `crop_id`.
6. Login buyer, then run Buyers > Upsert my buyer profile and Get my buyer profile.
7. With buyer token active, run Farms > Buyer cannot create farm to confirm 403. Restore farmer login before any remaining farm/crop operations.
8. Run Crops > Invalid harvest date to confirm 422.

The current Postman environment has blank `farm_id` and `crop_id` variables; successful create requests set them. Repeat creation may make additional sample records, which can be deactivated using DELETE on the resource IDs.

## Phase 4 marketplace and orders

| Method | Endpoint | Access | Behavior |
|---|---|---|---|
| POST | `/marketplace/products` | FARMER | Create a listing owned by the authenticated farmer |
| GET | `/marketplace/products` | Public | Search and filter available products; paginated |
| GET | `/marketplace/products/mine` | FARMER | List own listings |
| GET | `/marketplace/products/{product_id}` | Public | Product details |
| PATCH / DELETE | `/marketplace/products/{product_id}` | Listing owner | Update listing or soft-deactivate |
| POST | `/orders` | BUYER | Place an order and atomically reserve stock on the product document |
| GET | `/orders/buyer` | BUYER | List own buyer orders |
| GET | `/orders/seller` | FARMER | List orders for own products |
| GET | `/orders/{order_id}` | Buyer, seller, or ADMIN | Read an authorized order |
| POST | `/orders/{order_id}/cancel` | Owning BUYER | Cancel unpaid order and release its stock reservation |
| PATCH | `/orders/{order_id}/status` | Owning FARMER | Advance a paid order to processing, then ready for delivery |

Product filters: `search`, `county`, `category`, `min_price_kes`, `max_price_kes`, `limit`, and `offset`. Prices and order totals are integer Kenyan shillings (no floating-point money). Inventory is an integer count in the listing's declared unit (for example, whole bags, pieces, or kilograms). Ordering another farmer's listing is required; self-purchase is rejected. Listings and orders are not public for private fields; order reads are limited to the buyer, seller, or admin.

Stock reservation uses one MongoDB conditional update (`quantity_available >= requested`) on the product document. Concurrent orders cannot decrement below zero. Each order ID is recorded on the product as a private reservation marker. Cancellation restores stock only when that marker exists, then removes it, making retries safe against duplicate restock. If order creation fails after reservation, the service attempts to release it. Product stock edits use an optimistic quantity check and return 409 when a simultaneous order changed stock; reload and retry the edit.

Orders start as `AWAITING_PAYMENT` with `UNPAID`. Buyers can cancel only in this state. A seller cannot set `PAID`; that transition is intentionally reserved for the verified payment integration in Phase 5. Once payment verification marks an order paid, the seller can progress it through `PROCESSING` and `READY_FOR_DELIVERY`. After `READY_FOR_DELIVERY`, Phase 6 creates the delivery record; the buyer confirmation endpoint completes the order. Out-of-stock listings return 409 for order creation; invalid bodies/filters return 422; unauthorized access returns 401/403, and attempts to read another user's order return 404.

### Postman Phase 4 workflow

1. Login farmer, create a product listing, then browse/search and inspect it. The create request saves `product_id` and the farmer token is retained separately.
2. Login buyer and place an order for quantity 2. The request saves `order_id`; confirm `AWAITING_PAYMENT`/`UNPAID` and total amount equals quantity × integer unit price.
3. Use buyer order list, order detail, and the insufficient-stock negative request.
4. Login farmer and inspect seller orders. The seller `PAID` negative request must return 409. The farmer and buyer tokens are stored separately in Postman, so switching login does not overwrite them.
5. Cancel the unpaid order with the buyer token and repeat cancellation to exercise idempotent stock release. Do not mark payment successful manually; payment success is handled only by a verified provider callback.

The project runtime you reported returns MongoDB readiness as connected. In this agent execution environment, the configured Atlas hostname could not be resolved (`NoNameservers`), so live MongoDB integration could not be run here. The automated Phase 4 tests use isolated in-memory repositories; run the Postman workflow from the machine where `/health/ready` returns 200 to verify the real database.


## Phase 5 payments, escrow workflow and financial ledger

### Payment APIs

| Method | Endpoint | Access | Behavior |
|---|---|---|---|
| POST | `/payments/initiate` | BUYER, `Idempotency-Key` | Start STK Push for an owned unpaid order |
| POST | `/payments/callback/daraja` | Public provider callback | Match pending checkout, check amount/phone, query Daraja status, then process callback |
| POST | `/payments/mock/{payment_id}/callback` | Owning BUYER; development/test and mock provider only | Clearly marked simulation; never a real M-PESA payment |
| GET | `/payments/{payment_id}` | Owning BUYER or ADMIN | Get payment status |
| GET | `/payments/mine` | BUYER | Paginated buyer payment history |
| GET | `/payments/admin/history` | ADMIN | Paginated platform payment history |
| GET | `/payments/{payment_id}/provider-status` | Owning BUYER or ADMIN | Read-only provider status query; does not update local state |

Payment initiation requires an order in `AWAITING_PAYMENT`/`UNPAID`, the buyer's own order, a Kenyan mobile number, and an idempotency key 8–128 characters. The amount is taken from the stored order total, never accepted from the request. An accepted STK Push only sets payment status to `INITIATED`; it does not mark the order paid. Payment processing requires a callback CheckoutRequestID matching a Daraja payment, integer callback amount equal to the payment/order amount, callback phone matching the submitted phone, receipt reference, and a Daraja STK Push Query response for the same checkout with the same result code. Failure callbacks also require provider query confirmation to prevent forged callbacks from cancelling an order's payment attempt. Replayed matching callbacks are idempotent; conflicting callbacks are rejected.

Daraja OAuth uses `https://api.safaricom.co.ke/oauth/v1/generate` and production STK Push/STK Push Query use `https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest` and `/mpesa/stkpushquery/v1/query`, matching the production endpoint email supplied for this project. With `MPESA_ENVIRONMENT=sandbox`, the same paths use Safaricom's sandbox host. The selected environment's callback must be publicly reachable; production configuration requires HTTPS. Daraja does not sign the STK callback in this adapter, so the callback is not treated as proof by itself: it must pass the status query and payload correlation checks. Real Daraja requests require the consumer key/secret, shortcode, passkey and callback URL. Set `MPESA_SANDBOX_CALLBACK_URL` or `MPESA_PRODUCTION_CALLBACK_URL` to `https://<public-host>/payments/callback/daraja` only after the host is deployed or tunneled and reachable over HTTPS; never put production credentials in source control.

`PAYMENT_PROVIDER=mock` is the default and the required safe local choice. The mock STK initiation returns a generated mock checkout reference and pending status. The separate mock callback endpoint is available only when `APP_ENV=development` or `test` and `PAYMENT_PROVIDER=mock`; a successful simulation is stored as provider `mock`, with a `MOCK-…` receipt and ledger status `MOCK_SIMULATED`. It is not presented as real M-PESA or proof of regulated custody.

Payment configuration is validated on settings load and again before provider selection. `APP_ENV=development` or `test` with `MPESA_ENVIRONMENT=production` is rejected. Daraja sandbox requires `PAYMENT_PROVIDER=daraja`, `MPESA_ENVIRONMENT=sandbox`, and the separate `MPESA_SANDBOX_*` credential and callback variables; production credentials are never used for sandbox requests. Production requires the explicit combination `APP_ENV=production`, `PAYMENT_PROVIDER=daraja`, and `MPESA_ENVIRONMENT=production`, all `MPESA_PRODUCTION_*` credentials, and a publicly reachable HTTPS callback. Existing Render environments using generic `MPESA_*` credentials remain supported as a production-only fallback; migrate those secrets to `MPESA_PRODUCTION_*` when convenient. Do not set local development to production or test with production credentials. No payment request is sent merely by starting the application.

### Escrow-style workflow (not legal custody)

Payment confirmation creates an internal escrow workflow record with amount, configured commission, seller amount, status, provider and explicit `actual_funds_safeguarded`/`custody_status` values. With `ESCROW_PROVIDER=mock`, custody is `NOT_SAFEGUARDED` and no funds are held. A production safeguarded-funds partner requires an implementation of the partner adapter; selecting `ESCROW_PROVIDER=partner` without one fails closed. The application does not claim regulated escrow/custody.

| Method | Endpoint | Access | Behavior |
|---|---|---|---|
| GET | `/escrow/orders/{order_id}` | Buyer, seller or ADMIN | Find workflow by order |
| GET | `/escrow/{escrow_id}` | Buyer, seller or ADMIN | Get workflow and custody status |
| POST | `/escrow/{escrow_id}/release` | Owning FARMER or ADMIN | Request release; requires order `COMPLETED`, no unresolved dispute, and safeguarded funds for a real provider |
| POST | `/escrow/{escrow_id}/refund-request` | Owning BUYER | Record a refund request; mock records a request only, not an actual refund |

Release is blocked until delivery is confirmed, the order is `COMPLETED`, and no dispute is open or under review. A mock release records `SIMULATED_SETTLEMENT` and a `MOCK_SETTLEMENT_SIMULATED` ledger event; it does not record a confirmed seller payout or transfer money. Provider-confirmed settlement is the only path that records seller payout confirmation and platform commission. A provider error records `SETTLEMENT_FAILED` plus a payout-failed ledger event; the release can be retried with the same provider idempotency key.

### Append-only transaction ledger

`GET /transactions/orders/{order_id}/ledger` is available to the order buyer, seller, or ADMIN. Events are append-only and keyed idempotently. They record payment success/failure, safeguarding only when a provider confirms it, release request, seller settlement, commission, refund request/confirmation, and explicit mock simulation. Amounts use integer KES. There are no ledger update/delete operations.

### Postman Phase 5 workflow

1. Select the local environment and run Health; MongoDB readiness must return 200.
2. Login farmer and buyer. Keep both tokens in their separate environment variables.
3. Create a listing as farmer, then place an order as buyer; do not cancel it.
4. Send **Initiate payment (mock or Daraja)**. In mock development, it returns `INITIATED` only. Use one saved `Idempotency-Key` when retrying the same order.
5. For a development simulation, first try **Wrong amount mock callback** (409), then **Mock payment confirmation** (200), then **Duplicate mock callback** (200, no duplicate ledger event). For real Daraja, wait for Safaricom to call the public HTTPS callback and check the local payment/ledger endpoints; do not manually fabricate a success callback.
6. Fetch payment and escrow status, then inspect the append-only order ledger. Mock mode must show `actual_funds_safeguarded: false` and provider `mock`.
7. Complete delivery using the Phase 6 requests below. Mock payout mode records a simulation only. Refund requests only record a request unless a real refund-capable provider confirms it.

## Testing payment and escrow logic

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest -q
```

Phase 5 tests use in-memory repositories and provider fakes. They cover idempotent initiation/callbacks, failed and mismatched payments, Daraja checkout/amount/phone/result verification, production URL construction, private payment access, escrow commission arithmetic, dispute/delivery release gates, mock-only behavior and append-only ledger records. They do not call Safaricom or mutate MongoDB.


## Phase 6 delivery, disputes, refunds and payouts

### Delivery and dispute APIs

| Method | Endpoint | Access | Behavior |
|---|---|---|---|
| POST | `/deliveries/orders/{order_id}` | Owning FARMER | Create delivery for an order ready for delivery |
| GET | `/deliveries/mine` | BUYER or FARMER | Paginated deliveries for the current user |
| GET | `/deliveries/{delivery_id}` | Buyer, seller or ADMIN | Read tracking information |
| PATCH | `/deliveries/{delivery_id}/status` | Owning FARMER or ADMIN | Move through `PICKED_UP`, `IN_TRANSIT`, `DELIVERED`; records event timestamps |
| POST | `/deliveries/{delivery_id}/confirm` | Owning BUYER | Confirm receipt and move the order to `COMPLETED` |
| POST | `/disputes` | Order BUYER or FARMER | Open one dispute for a paid, unresolved order; sets order to `DISPUTED` |
| GET | `/disputes/mine` | BUYER or FARMER | List participant disputes |
| GET | `/disputes` | ADMIN | Paginated platform dispute list |
| GET | `/disputes/{dispute_id}` | Participant or ADMIN | View dispute and administrator audit history |
| PATCH | `/disputes/{dispute_id}/review` | ADMIN | Move to review/resolution and append an audited decision |

Evidence is represented by validated URLs; evidence file upload/hosting is not implemented yet. Dispute decisions are audit entries. `REFUND_BUYER` records an administrator decision but does not itself send money. Use the escrow refund request flow; an actual refund requires a configured provider that supports and confirms refunds. Unresolved disputes block payout.

### Payout APIs

| Method | Endpoint | Access | Behavior |
|---|---|---|---|
| GET | `/payouts/{escrow_id}` | Buyer, seller or ADMIN | Read payout/escrow status |
| POST | `/payouts/{escrow_id}/release` | Owning FARMER or ADMIN | Request seller settlement after buyer confirmation; provider and escrow safeguards apply |

`/escrow/{escrow_id}/release` remains available for compatibility. With the mock escrow provider in development/test, payout only becomes `SIMULATED_SETTLEMENT`; it is not a transfer. Production with mock is rejected. The partner escrow adapter is fail-closed until a real safeguarded-funds integration is implemented.

### Postman Phase 6 workflow

1. Complete the Phase 5 workflow through verified payment and save `order_id` and `escrow_id`.
2. Seller advances the order to `PROCESSING`, then `READY_FOR_DELIVERY` using `/orders/{order_id}/status`.
3. Under **Deliveries**, create the delivery as farmer, then run `PICKED_UP`, `IN_TRANSIT`, and `DELIVERED` in order.
4. Login as buyer and run **Buyer confirms delivery**. The order becomes `COMPLETED`.
5. Login as farmer and call **Request seller payout**. Development mock returns a simulation; real settlement requires a configured provider and confirmed settlement response.
6. For dispute testing, use a separate paid order before buyer confirmation: buyer opens the dispute, then admin starts review and records a decision. Payout remains blocked while status is `OPEN` or `UNDER_REVIEW`.

The Postman environment includes `delivery_id`. Keep farmer, buyer, and admin tokens in their separate environment variables. Only one dispute is allowed per order, so use a separate paid order for the dispute test and the normal payout test.

### Testing Phase 6

```powershell
python -m pytest -q
```

Phase 6 API tests use in-memory repositories and do not contact MongoDB or external payment providers. They check the delivery lifecycle, role/ownership restrictions, buyer confirmation, dispute authorization, audit entries, duplicate dispute protection, and invalid decisions. Swagger UI is available at `/docs` when the server is running.


## Phase 7 weather, agricultural advisory, market prices and SMS

### Weather and agricultural advisory APIs

| Method | Endpoint | Access | Behavior |
|---|---|---|---|
| GET | `/weather/forecast?latitude=...&longitude=...` | FARMER, AGRICULTURAL_OFFICER, ADMIN | Current conditions plus five-day three-hour forecast; requires `WEATHER_API_KEY` |
| POST | `/advisories` | AGRICULTURAL_OFFICER or ADMIN | Publish crop/county scoped or general officer guidance with a stated source |
| GET | `/advisories?crop_name=...&county=...` | FARMER, officer, admin | Farmer sees matching active advisories plus their own generated weather prompts |
| GET | `/advisories/mine` | FARMER | Paginated farm-linked recommendation history |
| POST | `/advisories/recommendations/weather` | FARMER | Fetch forecast and store transparent weather rules for an owned farm and crop |
| PATCH | `/advisories/{advisory_id}` | Authoring officer or ADMIN | Edit or deactivate an officer-authored advisory |

Weather uses OpenWeatherMap current conditions and its 5 day / 3 hour forecast API. Coordinates are supplied by the caller because existing farm records do not contain GPS coordinates. Successful responses are cached per rounded coordinate and provider key in process memory for `WEATHER_CACHE_TTL_SECONDS` (default 300, maximum 3600); `cache_hit` and `cache_valid_until` make freshness explicit. Set the TTL to `0` to disable caching. This is not a request-rate limiter and is not shared across multiple app workers. The provider key is required; missing configuration and provider failures return 503 without fabricated weather. See the [current weather API documentation](https://openweathermap.org/api/current) and [5 day forecast API documentation](https://openweathermap.org/api/forecast5).

Weather recommendations are rule-based prompts, saved with the crop, farm, provider snapshot, and rules applied. The implemented rainfall rules ask farmers to check soil moisture/crop stage when forecast rainfall is low, or monitor drainage when it is high. They do not prescribe planting dates, irrigation volumes, pesticides, or guaranteed outcomes; farmers are directed to confirm decisions with county extension staff.

### Crop stage calendar and soil guidance

`GET /crop-planning/crops/{crop_id}/calendar` returns source-linked stage checklists for maize, tomato, and potato, only for the authenticated farmer's own crop and farm. This is stage-order guidance, not a county planting calendar: the project does not infer planting seasons or fixed day intervals. Other crop names return 404 until their own reviewed reference content is added.

`POST /crop-planning/soil-guidance` saves general soil education in the farmer's advisory history. It recommends using a soil-test report with qualified extension support and does not calculate fertilizer rates, select a product, interpret soil chemistry, or prescribe an application schedule. This reflects Kenya's Ministry of Agriculture soil-management policy and training resources, which emphasize site-specific soil testing. Sources: [Agricultural Soil Management Policy 2023](https://kilimo.go.ke/wp-content/uploads/2025/02/Agricultural-Soil-Management-Policy-2023.pdf), [soil sampling and testing training manual](https://kilimo.go.ke/wp-content/uploads/2025/07/Training-Manual.pdf).

### Pest education

`GET /pest-knowledge` and `/pest-knowledge/{slug}` currently provide traceable, non-chemical educational entries for fall armyworm on maize and whitefly on tomato. This is not a pest image classifier, and the 11-label disease model is not used for pest detection. The initial entries refer to [KALRO maize integrated pest management guidance](https://www.kalro.org/navcdp/docs/MAIZE%20TIMPS%20Volume%202%20for%20upload.pdf), [FAO fall armyworm scouting guidance](https://www.fao.org/fileadmin/templates/fcc/Fall_Armyworm/web_FINAL-guidance-note-2.pdf), and [KALRO tomato whitefly TIMPs](https://www.kalro.org/navcdp/docs/tot_timps/TOMATO%20TIMPS.pdf). No chemical product or rate is generated.

### Market price APIs

| Method | Endpoint | Access | Behavior |
|---|---|---|---|
| POST | `/market-prices` | AGRICULTURAL_OFFICER or ADMIN | Record an observed price, unit, collection date, source type, and source name |
| GET | `/market-prices` | Authenticated farmer, buyer, officer, admin | Filter and paginate recorded observations |
| GET | `/market-prices/history?crop_name=...` | Authenticated user | Retrieve dated price history |
| GET | `/market-prices/compare?crop_name=...&county=...` | Authenticated user | Compare latest recorded observation by market, county, and unit |
| POST | `/market-prices/{price_id}/revision` | AGRICULTURAL_OFFICER or ADMIN | Append a correction linked to its prior record; old history stays intact |

There is no automatic market price feed in this phase. API records must come from an actual survey or named external source; do not treat Postman placeholders as Kenyan market prices. Prices are integer KES and include source metadata.

### SMS APIs and configuration

| Method | Endpoint | Access | Behavior |
|---|---|---|---|
| POST | `/notifications/send` | AGRICULTURAL_OFFICER or ADMIN | Send a supplied event message to a registered user; requires `Idempotency-Key` |
| GET | `/notifications/mine` | Authenticated user | Paginated notification attempt history for that user |

Supported event labels are `REGISTRATION`, `NEW_ORDER`, `PAYMENT_CONFIRMATION`, `DELIVERY_UPDATE`, `DISPUTE_UPDATE`, `SELLER_PAYOUT`, and `AGRICULTURAL_ADVISORY`. An officer/admin can send an event message directly. Domain routes also queue event SMS for registration, new orders, verified payment, delivery, dispute, payout, and farmer weather guidance when `SMS_AUTO_DISPATCH=true`; background dispatch is best-effort and does not roll back the business operation. It defaults to false. The SMS history records accepted/simulated/failed attempts.

For Africa's Talking Sandbox, set `SMS_PROVIDER=africas_talking`, `SMS_ENVIRONMENT=sandbox`, `SMS_USERNAME=sandbox`, and `SMS_API_KEY` to the key generated for the Sandbox app. Sandbox requests are reported as `SIMULATED` and appear in its simulator; they do not reach a handset. Keep `SMS_AUTO_DISPATCH=false` while validating. Production requires `SMS_ENVIRONMENT=production`, the production app username/key, and any approved sender ID; provider acceptance is stored as `ACCEPTED`, not proof of handset delivery. The adapter does not log API keys, phone numbers, message bodies, or provider response text. `SMS_PROVIDER=http` remains available for generic JSON/Bearer gateways with `SMS_API_URL`, `SMS_API_KEY`, and optional `SMS_SENDER_ID`. `SMS_PROVIDER=mock` is development/test-only. Provider errors are stored as `FAILED`; API keys and recipient phone numbers are not returned in notification history.

### Phase 7 Postman workflow and tests

1. Configure `WEATHER_API_KEY` in the backend environment to use weather endpoints. The Postman request checks for either a valid forecast or explicit 503 when the provider is unavailable.
2. Bootstrap/login admin, create the officer account, and run **Login officer**.
3. Create an advisory as officer; login as farmer and filter by crop and county. For weather prompts, use a farmer-owned farm/crop and coordinate values.
4. Enter a real observed market price, collection date, location, unit, and source in the Postman environment before running **Add observed price**. Exercise filters, comparison, history, and a revision.
5. With Africa's Talking Sandbox configured, run **Send event SMS** as an admin/officer with a registered recipient and unique `Idempotency-Key`. Confirm `SIMULATED` and check the Africa's Talking simulator (no handset receives it). Do not enable automatic dispatch until this manual check succeeds. Production requires production credentials and a configured approved sender ID; a successful response means accepted, not delivered.
6. `python -m pytest -q` runs isolated tests using fake weather/SMS providers and in-memory repositories; tests do not call external providers or production MongoDB.

## Phase 8 disease image screening and Phase 9 verification

| Method | Endpoint | Access | Behavior |
|---|---|---|---|
| POST | `/disease-detection/predict` | FARMER | Upload JPEG, PNG, or WebP in multipart field `image`; model-backed screening and saved metadata |
| GET | `/disease-detection/mine` | FARMER | Paginated prediction history for the current farmer only |
| GET | `/disease-detection/knowledge` | Public | List source-backed general guidance; optional `crop_name=Maize`, `Potato`, or `Tomato` |
| GET | `/disease-detection/knowledge/{model_label}` | Public | Return the display name, symptoms, non-chemical general guidance, disclaimer, and source links for an exact model label |

Prediction requires a trained Keras model and a JSON class list that exactly matches the model output order. Images are size-limited and rejected above 25 million pixels; only a content hash and metadata are stored in MongoDB. Model assets are not version-controlled; if the deployment cannot load them, prediction returns HTTP 503. No field accuracy is claimed. In Postman, use **Disease Detection > Predict from crop image**, then **List my screening history**. Copy the returned `predicted_label` into `disease_label` and send **Get guidance for a model label** to view source links and non-chemical general guidance.

`DISEASE_CONFIDENCE_THRESHOLD` (default `0.60`, range 0–1) marks low-confidence model outputs as uncertain. The API recommends a clearer image and officer review for uncertain results. This threshold is a user-experience rule, not a calibrated probability or diagnostic performance guarantee. The trained model's reported PlantVillage test metrics do not establish accuracy on Kenyan field images.

### Phase 5 disease history and farmer monitoring

Disease reports now support farmer-entered activity history, model-screened follow-up images, case resolution, and officer review requests. The original follow-up image bytes are not retained; a SHA-256 hash, file metadata, prediction, and optional observation are stored. A follow-up label comparison is only a comparison of model outputs; it does not independently prove the crop improved or worsened. No follow-up interval or recovery date is invented.

| Method | Endpoint | Access | Behavior |
|---|---|---|---|
| POST | `/disease-detection/{report_id}/treatments` | Owning FARMER | Idempotently record a farmer-entered cultural, biological, chemical, or other activity. This is history, not a recommendation. Chemical records require an approved PCPB evidence record matching crop and disease. |
| POST | `/disease-detection/{report_id}/followups` | Owning FARMER | Multipart `image` and optional observation; performs model screening and records hash/metadata. Requires `Idempotency-Key`. |
| GET | `/disease-detection/{report_id}/monitoring` | Owning FARMER | Retrieve initial report, action history, follow-up history, and status. |
| POST | `/disease-detection/{report_id}/review-request` | Owning FARMER | Request a review; records `REVIEW_REQUESTED`. Repeated request/resolved state returns 409. |
| POST | `/disease-detection/{report_id}/resolve` | Owning FARMER | Mark the case resolved as a farmer-reported status. Does not validate disease absence. |
| GET | `/disease-detection/review-queue` | AGRICULTURAL_OFFICER or ADMIN | Paginated farmer-requested reviews. |
| PATCH | `/disease-detection/{report_id}/review` | AGRICULTURAL_OFFICER or ADMIN | Append an officer note and return the case to `OPEN`; repeated/non-pending review returns 409. |

Follow-up and treatment writes use an `Idempotency-Key` header. The Postman folder contains each endpoint; select the farmer or officer token according to the request. A model-less deployment returns 503 for follow-up screening. Existing disease reports without case fields are treated as `OPEN` by the response schema; no migration deletes or rewrites existing records.

### Phase 13 officer and administrator workspace

The React workspace now includes a role-gated Officer/Admin desk. Officers and administrators can see farmer-requested disease-review cases, append review notes, and publish source-attributed advisories. Administrators also get record totals for users, disputes, payment history, and recorded market observations and can create agricultural-officer accounts. The server still enforces each endpoint's role; hiding a UI action is not treated as authorization. Payment totals are record counts, not balances or proof of settlement.

### Phase 14 farmer frontend and language support

The existing mobile-responsive React frontend now links the stage calendar, soil guidance, pest education, disease report history, activity logs, follow-up image screening, case review request/resolution, and the officer/admin desk to their backend APIs. A small English/Kiswahili interface toggle covers navigation and selected crop-health/planning labels. Knowledge-base content, model-provided text, some dialogs, and operational messages remain English; the UI is not yet fully translated. Existing responsive layout and reduced-motion CSS remain in place. Original follow-up images are not retained.

Final local verification:

```powershell
.\venv\Scripts\Activate.ps1
python -m pytest -q
python -m compileall -q app tests
```

The automated suite uses isolated in-memory repositories and mocked external providers; it does not call production M-Pesa, SMS, or weather services and does not use the production database. Import the collection and environment under `postman/` for manual API workflows. Never put production credentials into a shared Postman environment.

### PCPB pesticide evidence workflow

The project accepts PCPB evidence records only as drafts. `POST /pesticide-records` is available to an administrator or agricultural officer, and only an administrator may approve/reject a pending record through `PATCH /pesticide-records/{record_id}/review`. Approval requires explicit confirmation that both the current PCPB registration entry and its approved label were checked. Farmer-visible `GET /pesticide-records/approved` lists records only after approval. No pesticide rates or treatment prescriptions are generated. There are no seeded product records; the Postman examples are placeholders and must be replaced with verified data before submission.

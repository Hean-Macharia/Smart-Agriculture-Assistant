# Smart Agriculture Advisory and Market Linkage API

This FastAPI backend is being built in phases. **Phases 1 through 8 are implemented**: configuration and health, JWT authentication and role checks, farmer/buyer profiles, farms and crops, marketplace listings and stock-reserving orders, payment adapters, verified Daraja callbacks, internal escrow workflow, an append-only transaction ledger, delivery tracking, dispute review, refund request recording, payout status/release handling, weather forecasts, farm-linked weather guidance, market price records/history, SMS adapter operations, and model-backed crop image screening. A trained disease model and matching label file must be supplied before inference can return predictions.

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

If `.env` already exists, keep it and add the settings listed below instead of overwriting it. Set `MONGODB_URI` and `DATABASE_NAME`. Set `JWT_SECRET_KEY` and `ADMIN_BOOTSTRAP_TOKEN` to separate random values of at least 32 characters. Do not commit `.env` or paste its secrets into shared Postman environments. No default administrator password is embedded in the application.

### Disease model setup

The endpoints are `POST /disease-detection/predict` (farmer JWT, multipart form field `image`) and `GET /disease-detection/mine` (farmer JWT). Upload JPEG, PNG, or WebP up to `DISEASE_IMAGE_MAX_BYTES` (8 MiB by default). The service decodes with OpenCV, resizes to `DISEASE_INPUT_SIZE` (224 by default), converts to RGB, and scales pixels to 0–1. It stores prediction metadata and the image SHA-256 in MongoDB, not the original image. The response says that the model output is preliminary screening, not a diagnosis.

Install TensorFlow when a trained model is available: `python -m pip install -r requirements-ml.txt`. Configure `DISEASE_MODEL_PATH` to a trusted Keras `.keras` model and `DISEASE_LABELS_PATH` to a JSON list in the model output order, for example `[\"Maize___Common_Rust\", \"Maize___Healthy\"]` (or `{\"classes\": [...]}`). The model must accept input shaped `(1, 224, 224, 3)` and output one score per label; adjust `DISEASE_INPUT_SIZE` to match its training input. No model weights or accuracy claims are bundled. Without model assets and TensorFlow, inference returns HTTP 503 rather than a fabricated prediction. TensorFlow is optional because it is a large runtime; its official pip guide lists Python 3.10–3.13 and native Windows CPU support, while GPU inference on Windows uses WSL2: [TensorFlow installation guide](https://www.tensorflow.org/install/pip).

For local MongoDB, defaults are `mongodb://localhost:27017` and database `smart_agriculture`. The API starts for diagnosis if MongoDB is down, but database-backed registration and login return unavailable until MongoDB responds.

## Run the API

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

Daraja OAuth uses `https://api.safaricom.co.ke/oauth/v1/generate` and production STK Push/STK Push Query use `https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest` and `/mpesa/stkpushquery/v1/query`, matching the production endpoint email supplied for this project. With `MPESA_ENVIRONMENT=sandbox`, the same paths use Safaricom's sandbox host. `MPESA_CALLBACK_URL` must be publicly reachable; production configuration requires HTTPS. Daraja does not sign the STK callback in this adapter, so the callback is not treated as proof by itself: it must pass the status query and payload correlation checks. Real Daraja requests require the consumer key/secret, shortcode, passkey and callback URL. Provider selection is environment-specific. Set `MPESA_CALLBACK_URL` to `https://<public-host>/payments/callback/daraja` only after the host is deployed or tunneled and reachable over HTTPS; never put production credentials in source control.

`PAYMENT_PROVIDER=mock` is the default. The mock STK initiation returns a generated mock checkout reference and pending status. The separate mock callback endpoint is available only when `APP_ENV=development` or `test` and `PAYMENT_PROVIDER=mock`; a successful simulation is stored as provider `mock`, with a `MOCK-…` receipt and ledger status `MOCK_SIMULATED`. It is not presented as real M-PESA or proof of regulated custody. Set `PAYMENT_PROVIDER=daraja` to use the real adapter. Missing Daraja configuration returns an explicit service error, not fake success.

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

Weather uses OpenWeatherMap current conditions and its 5 day / 3 hour forecast API. Coordinates are supplied by the caller because existing farm records do not contain GPS coordinates. The weather provider key is required; missing configuration and provider failures return 503 without fabricated weather. See the [current weather API documentation](https://openweathermap.org/api/current) and [5 day forecast API documentation](https://openweathermap.org/api/forecast5).

Weather recommendations are rule-based prompts, saved with the crop, farm, provider snapshot, and rules applied. The implemented rainfall rules ask farmers to check soil moisture/crop stage when forecast rainfall is low, or monitor drainage when it is high. They do not prescribe planting dates, irrigation volumes, pesticides, or guaranteed outcomes; farmers are directed to confirm decisions with county extension staff.

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

Prediction requires a trained Keras model and a JSON class list that exactly matches the model output order. Images are size-limited and rejected above 25 million pixels; only a content hash and metadata are stored in MongoDB. No model or image dataset is included, so missing model/dependency configuration returns HTTP 503. No prediction accuracy is claimed by this project. In Postman, use **Disease Detection > Predict from crop image**, choose a file, then run **List my screening history** after a successful 201 response. Until model assets are set up, the test accepts and explains a 503 response.

Final local verification:

```powershell
.\venv\Scripts\Activate.ps1
python -m pytest -q
python -m compileall -q app tests
```

The automated suite uses isolated in-memory repositories and mocked external providers; it does not call production M-Pesa, SMS, or weather services and does not use the production database. Import the collection and environment under `postman/` for manual API workflows. Never put production credentials into a shared Postman environment.

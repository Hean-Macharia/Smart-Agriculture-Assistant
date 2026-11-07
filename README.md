# Smart Agriculture Advisory and Market Linkage API

This FastAPI backend is being built in phases. **Phases 1 through 4 are implemented**: configuration and health, JWT authentication and role checks, farmer/buyer profiles, farms and crops, marketplace listings, and stock-reserving orders. Payment verification, escrow, delivery, disputes, weather/advisory, and disease detection are later phases.

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

Orders start as `AWAITING_PAYMENT` with `UNPAID`. Buyers can cancel only in this state. A seller cannot set `PAID`; that transition is intentionally reserved for the verified payment integration in Phase 5. Once payment verification marks an order paid, the seller can progress it through `PROCESSING` and `READY_FOR_DELIVERY`. Delivery, buyer confirmation, and completion are later phases. Out-of-stock listings return 409 for order creation; invalid bodies/filters return 422; unauthorized access returns 401/403, and attempts to read another user's order return 404.

### Postman Phase 4 workflow

1. Login farmer, create a product listing, then browse/search and inspect it. The create request saves `product_id` and the farmer token is retained separately.
2. Login buyer and place an order for quantity 2. The request saves `order_id`; confirm `AWAITING_PAYMENT`/`UNPAID` and total amount equals quantity × integer unit price.
3. Use buyer order list, order detail, and the insufficient-stock negative request.
4. Login farmer and inspect seller orders. The seller `PAID` negative request must return 409. The farmer and buyer tokens are stored separately in Postman, so switching login does not overwrite them.
5. Cancel the unpaid order with the buyer token and repeat cancellation to exercise idempotent stock release. Do not mark payment successful manually; Phase 5 will add verified provider callbacks.

The configured MongoDB is currently unavailable in this environment (the readiness endpoint returns `{"detail":{"status":"not_ready","database":"unavailable"}}`). The Phase 4 tests use isolated in-memory repositories and never claim to validate MongoDB runtime behavior. Start/restore MongoDB, then confirm `/health/ready` returns 200 before using the listing/order collection against a live database.

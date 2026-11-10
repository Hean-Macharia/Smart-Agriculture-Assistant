# Manual API Testing Guide — Smart Agriculture Backend

**Project:** `C:\Users\ADMIN\Documents\smart-agricultural-system\backend`  
**Local base URL:** `http://127.0.0.1:8000`  
**Verified API coverage:** **75 HTTP method/path combinations across 59 distinct paths**, counted from this app’s OpenAPI schema.  
**Manual Test Status:** all entries start as **NOT TESTED**; this document does not send requests or alter the database.

This guide uses the current FastAPI routes and Pydantic schemas as source of truth. It is for local/test use. Sample account and market values are test data, not real market observations. Phone numbers may belong to real subscribers: keep SMS on local `mock` or the Africa’s Talking Sandbox. Never run the examples with production SMS recipients. Set local `PAYMENT_PROVIDER=mock`; `daraja` can trigger a real M-Pesa prompt. Do not fabricate successful Daraja callbacks.

## SECTION A: Preparation

### Start the server and check MongoDB

From PowerShell:

```powershell
cd C:\Users\ADMIN\Documents\smart-agricultural-system\backend
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Keep Uvicorn running. Use a private local `.env` with your own `MONGODB_URI`, `DATABASE_NAME`, `JWT_SECRET_KEY` (at least 32 random characters), and separate `ADMIN_BOOTSTRAP_TOKEN` (at least 32 random characters). Do not paste these into this document or a shared Postman environment. For a no-real-payment local run use `APP_ENV=development`, `PAYMENT_PROVIDER=mock`, `ESCROW_PROVIDER=mock`, `SMS_PROVIDER=mock`, `SMS_AUTO_DISPATCH=false`. Mock SMS makes no network call.

Send `GET http://127.0.0.1:8000/health` to check API liveness. Send `GET http://127.0.0.1:8000/health/ready` to ping MongoDB. Readiness `503` means database URI/credentials, Atlas IP access list, DNS, or server availability needs attention before database-backed tests. Use a dedicated test database; do not test outages by disrupting production Atlas. Swagger UI is `http://127.0.0.1:8000/docs`; OpenAPI JSON is `http://127.0.0.1:8000/openapi.json`.

### Create and send each Postman request manually

1. Choose **New → HTTP**, set the method and full local URL from each test below.
2. For protected routes open **Authorization → Bearer Token** and paste the token for the stated role. Paste only the token; Postman adds `Bearer`.
3. For JSON requests choose **Body → raw → JSON**. Add `Content-Type: application/json` if Postman has not added it. Add only the other endpoint-specific headers shown (for example `Idempotency-Key`).
4. For GET/DELETE without a body choose **Body → none**. A successful DELETE returns 204 with no JSON body.
5. Copy actual IDs from responses (`user.id`, `id`, etc.) into later path/body placeholders such as `{{farm_id}}`, or save them as local Postman environment values. Never guess an ObjectId.
6. Login returns `access_token`; copy it into Bearer Token. Keep farmer, buyer, officer, and admin tokens separate.
7. For image upload choose **Body → form-data**, enter key `image`, switch its type from Text to **File**, and choose JPEG/PNG/WebP. Do not set multipart Content-Type manually; Postman must generate its boundary.

### Reusable local test identities

Farmer: `Test Farmer One`, `farmer1@example.com`, `0712345678`; buyer: `Test Buyer One`, `buyer1@example.com`, `0723456789`. Sample password: `LocalTestPass!234` (local test only). Bootstrap account: `admin1@example.com`, `0734567890`. If an email/phone is already registered, the actual API returns 409; use a new test email rather than deleting records. The sample listing is tomatoes, 100 kg at KES 80/kg. Market-price sample records below are explicitly synthetic, not current Kenyan market quotes.

Workflow: register/login users → profiles → farmer farm/crop/listing → buyer browse/order → local mock payment callback → automatically created internal escrow record → seller order processing → delivery → buyer confirmation → simulated payout. Use a separate paid order for dispute testing, because an unresolved dispute blocks release. Escrow creation is automatic after payment confirmation; there is no separate create-escrow endpoint.


## SECTION B: Health APIs

### Test 1: Liveness check

**Method:** GET  
**URL:** `http://127.0.0.1:8000/health`  
**Authentication:** Not required  
**Required role:** Public  
**Headers:**
```text
None
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"status":"ok","service":"Smart Agriculture Advisory and Market Linkage API"}`

**What to verify:** Liveness check succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** `/health` has no input to invalidate; readiness returns 503 when the test MongoDB is unavailable. Never disrupt production to test this.

### Test 2: MongoDB readiness check

**Method:** GET  
**URL:** `http://127.0.0.1:8000/health/ready`  
**Authentication:** Not required  
**Required role:** Public  
**Headers:**
```text
None
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK; 503 if MongoDB is unavailable

**Expected response:** `{"status":"ready","database":"connected"}`

**What to verify:** MongoDB readiness check succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** `/health` has no input to invalidate; readiness returns 503 when the test MongoDB is unavailable. Never disrupt production to test this.


## SECTION C: Authentication APIs

Password reset/change is not implemented. Public registration cannot set a role. Admin managed-user endpoints are detailed in Section S.

### Test 3: Register a farmer account

**Method:** POST  
**URL:** `http://127.0.0.1:8000/auth/register/farmer`  
**Authentication:** Not required  
**Required role:** Public  
**Headers:**
```text
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "full_name": "Test Farmer One",
  "email": "farmer1@example.com",
  "phone": "0712345678",
  "password": "LocalTestPass!234"
}
```

**Expected HTTP status:** 201 Created

**Expected response:** `{"id":"<ObjectId>","full_name":"Test Farmer One","email":"farmer1@example.com","phone":"+254712345678","role":"FARMER","is_active":true,"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Register a farmer account succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Copy `id`; then login and save `access_token`.

**Negative test:** Duplicate email/phone → 409; malformed email/phone or missing fields → 422.

### Test 4: Register a buyer account

**Method:** POST  
**URL:** `http://127.0.0.1:8000/auth/register/buyer`  
**Authentication:** Not required  
**Required role:** Public  
**Headers:**
```text
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "full_name": "Test Buyer One",
  "email": "buyer1@example.com",
  "phone": "0723456789",
  "password": "LocalTestPass!234"
}
```

**Expected HTTP status:** 201 Created

**Expected response:** `{"id":"<ObjectId>","full_name":"Test Buyer One","email":"buyer1@example.com","phone":"+254723456789","role":"BUYER","is_active":true,"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Register a buyer account succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Copy `id`; then login and save `access_token`.

**Negative test:** Duplicate email/phone → 409; adding a public `role` field → 422.

### Test 5: Create the first administrator

**Method:** POST  
**URL:** `http://127.0.0.1:8000/auth/bootstrap-admin`  
**Authentication:** Not required  
**Required role:** Public + X-Admin-Bootstrap-Token  
**Headers:**
```text
X-Admin-Bootstrap-Token: (private server value; do not share)
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "full_name": "Test Admin One",
  "email": "admin1@example.com",
  "phone": "0734567890",
  "password": "LocalTestPass!234"
}
```

**Expected HTTP status:** 201 Created

**Expected response:** `{"id":"<ObjectId>","full_name":"Test Admin One","email":"admin1@example.com","phone":"+254734567890","role":"ADMIN","is_active":true,"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Create the first administrator succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Copy returned `id`, login, and keep the admin token private.

**Negative test:** Wrong token → 403; bootstrap not configured → 503; existing admin → 409.

### Test 6: Log in and receive a JWT access token

**Method:** POST  
**URL:** `http://127.0.0.1:8000/auth/login`  
**Authentication:** Not required  
**Required role:** Public  
**Headers:**
```text
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "email": "farmer1@example.com",
  "password": "LocalTestPass!234"
}
```

**Expected HTTP status:** 200 OK

**Expected response:** `{"access_token":"<string>","expires_in":1,"user":{"id":"<ObjectId>","full_name":"Test Farmer One","email":"farmer1@example.com","phone":"+254712345678","role":"FARMER","is_active":true,"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}}`

**What to verify:** Log in and receive a JWT access token succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Copy `access_token` and `user.id`; use that role’s token in the Authorization tab.

**Negative test:** Wrong password/nonexistent email → 401; malformed email or missing field → 422.

### Test 7: Get the authenticated user

**Method:** GET  
**URL:** `http://127.0.0.1:8000/auth/me`  
**Authentication:** Required  
**Required role:** Any authenticated user  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"id":"<ObjectId>","full_name":"Test Farmer One","email":"farmer1@example.com","phone":"+254712345678","role":"FARMER","is_active":true,"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Get the authenticated user succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** No new resource; confirms the identity represented by this token.

**Negative test:** Missing, malformed, or expired token → 401 (default token lifetime 30 minutes).

### Test 8: Update the authenticated user's profile

**Method:** PATCH  
**URL:** `http://127.0.0.1:8000/auth/me`  
**Authentication:** Required  
**Required role:** Any authenticated user  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "full_name": "Test Farmer One Updated"
}
```

**Expected HTTP status:** 200 OK

**Expected response:** `{"id":"<ObjectId>","full_name":"Test Farmer One","email":"farmer1@example.com","phone":"+254712345678","role":"FARMER","is_active":true,"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Update the authenticated user's profile succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** No new resource; confirms the identity represented by this token.

**Negative test:** Missing, malformed, or expired token → 401 (default token lifetime 30 minutes).

**Invalid/expired token:** `/auth/me` with `Bearer not-a-jwt`, missing bearer, or a token older than `ACCESS_TOKEN_EXPIRE_MINUTES` (default 30) returns 401. Do not edit signed tokens to manufacture expiry.


## SECTION D: Farmer Management

### Test 9: Get my farmer profile

**Method:** GET  
**URL:** `http://127.0.0.1:8000/farmers/me`  
**Authentication:** Required  
**Required role:** FARMER  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"county":"<string>","sub_county":"<string>","location":"<string>","farm_size_acres":2.5,"soil_type":"<string>","irrigation_available":true,"crops_grown":["maize","beans"],"id":"<ObjectId>","user_id":"<user ObjectId>","created_at":"<ISO-8601 datetime>","updated_at":"<ISO-8601 datetime>"}`

**What to verify:** Get my farmer profile succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

### Test 10: Create or update my farmer profile

**Method:** PUT  
**URL:** `http://127.0.0.1:8000/farmers/me`  
**Authentication:** Required  
**Required role:** FARMER  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "county": "Kiambu",
  "sub_county": "Limuru",
  "location": "Ndeiya",
  "farm_size_acres": 2.5,
  "soil_type": "Clay loam",
  "irrigation_available": true,
  "crops_grown": [
    "maize",
    "beans"
  ]
}
```

**Expected HTTP status:** 200 OK

**Expected response:** `{"county":"<string>","sub_county":"<string>","location":"<string>","farm_size_acres":2.5,"soil_type":"<string>","irrigation_available":true,"crops_grown":["maize","beans"],"id":"<ObjectId>","user_id":"<user ObjectId>","created_at":"<ISO-8601 datetime>","updated_at":"<ISO-8601 datetime>"}`

**What to verify:** Create or update my farmer profile succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.


## SECTION E: Buyer Management

### Test 11: Get my buyer profile

**Method:** GET  
**URL:** `http://127.0.0.1:8000/buyers/me`  
**Authentication:** Required  
**Required role:** BUYER  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"county":"<string>","sub_county":"<string>","delivery_location":"<string>","organization_name":"<string or null>","id":"<ObjectId>","user_id":"<user ObjectId>","created_at":"<ISO-8601 datetime>","updated_at":"<ISO-8601 datetime>"}`

**What to verify:** Get my buyer profile succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

### Test 12: Create or update my buyer profile

**Method:** PUT  
**URL:** `http://127.0.0.1:8000/buyers/me`  
**Authentication:** Required  
**Required role:** BUYER  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "county": "Nairobi",
  "sub_county": "Westlands",
  "delivery_location": "Westlands, Nairobi",
  "organization_name": "Local Produce Shop"
}
```

**Expected HTTP status:** 200 OK

**Expected response:** `{"county":"<string>","sub_county":"<string>","delivery_location":"<string>","organization_name":"Local Produce Shop","id":"<ObjectId>","user_id":"<user ObjectId>","created_at":"<ISO-8601 datetime>","updated_at":"<ISO-8601 datetime>"}`

**What to verify:** Create or update my buyer profile succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.


## SECTION F: Farm Management

### Test 13: Register a farm

**Method:** POST  
**URL:** `http://127.0.0.1:8000/farms`  
**Authentication:** Required  
**Required role:** FARMER  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "name": "Amina Demo Farm",
  "county": "Kiambu",
  "sub_county": "Limuru",
  "location": "Ndeiya",
  "size_acres": 2.5,
  "soil_type": "Clay loam",
  "irrigation_available": true
}
```

**Expected HTTP status:** 201 Created

**Expected response:** `{"name":"<string>","county":"<string>","sub_county":"<string>","location":"<string>","size_acres":1.0,"soil_type":"<string>","id":"<ObjectId>","owner_id":"<string>","is_active":true,"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Register a farm succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Copy farm `id` to `farm_id`; then create a crop.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

### Test 14: List my active farms

**Method:** GET  
**URL:** `http://127.0.0.1:8000/farms?limit=20&offset=0`  
**Authentication:** Required  
**Required role:** FARMER  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"items":[{"name":"<string>","county":"<string>","sub_county":"<string>","location":"<string>","size_acres":1.0,"soil_type":"<string>","id":"<ObjectId>","owner_id":"<string>","is_active":true,"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}],"total":1,"limit":1,"offset":1}`

**What to verify:** List my active farms succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Copy farm `id` to `farm_id`; then create a crop.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

### Test 15: Get one of my farms

**Method:** GET  
**URL:** `http://127.0.0.1:8000/farms/{{farm_id}}`  
**Authentication:** Required  
**Required role:** FARMER owner  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"name":"<string>","county":"<string>","sub_county":"<string>","location":"<string>","size_acres":1.0,"soil_type":"<string>","id":"<ObjectId>","owner_id":"<string>","is_active":true,"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Get one of my farms succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Try a malformed ObjectId (422) and a well-formed nonexistent ID (404); for a real record, test with a non-owner token (404).

### Test 16: Update one of my farms

**Method:** PATCH  
**URL:** `http://127.0.0.1:8000/farms/{{farm_id}}`  
**Authentication:** Required  
**Required role:** FARMER owner  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "size_acres": 3
}
```

**Expected HTTP status:** 200 OK

**Expected response:** `{"name":"<string>","county":"<string>","sub_county":"<string>","location":"<string>","size_acres":1.0,"soil_type":"<string>","id":"<ObjectId>","owner_id":"<string>","is_active":true,"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Update one of my farms succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Try malformed ID → 422, nonexistent/other user’s resource → 404, or unauthenticated request → 401.

### Test 17: Deactivate one of my farms

**Method:** DELETE  
**URL:** `http://127.0.0.1:8000/farms/{{farm_id}}`  
**Authentication:** Required  
**Required role:** FARMER owner  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 204 No Content

**Expected response:** No body (204 No Content).

**What to verify:** Deactivate one of my farms succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Try malformed ID → 422, nonexistent/other user’s resource → 404, or unauthenticated request → 401.


## SECTION G: Crop Management

### Test 18: Record a crop on one of my farms

**Method:** POST  
**URL:** `http://127.0.0.1:8000/crops`  
**Authentication:** Required  
**Required role:** FARMER  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "farm_id": "{{farm_id}}",
  "name": "Maize",
  "variety": "Hybrid demo",
  "planting_date": "2026-03-01",
  "expected_harvest_date": "2026-07-01",
  "quantity": 250,
  "quantity_unit": "kg",
  "growth_information": "Vegetative stage"
}
```

**Expected HTTP status:** 201 Created

**Expected response:** `{"farm_id":"<string>","name":"<string>","planting_date":"2026-01-15","id":"<ObjectId>","owner_id":"<string>","is_active":true,"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Record a crop on one of my farms succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Copy crop `id` to `crop_id`.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

### Test 19: List my active crops, optionally filtered by farm

**Method:** GET  
**URL:** `http://127.0.0.1:8000/crops?farm_id={{farm_id}}&limit=20&offset=0`  
**Authentication:** Required  
**Required role:** FARMER  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"items":[{"farm_id":"<string>","name":"<string>","planting_date":"2026-01-15","id":"<ObjectId>","owner_id":"<string>","is_active":true,"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}],"total":1,"limit":1,"offset":1}`

**What to verify:** List my active crops, optionally filtered by farm succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Copy crop `id` to `crop_id`.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

### Test 20: Get one of my crops

**Method:** GET  
**URL:** `http://127.0.0.1:8000/crops/{{crop_id}}`  
**Authentication:** Required  
**Required role:** FARMER owner  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"farm_id":"<string>","name":"<string>","planting_date":"2026-01-15","id":"<ObjectId>","owner_id":"<string>","is_active":true,"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Get one of my crops succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Try a malformed ObjectId (422) and a well-formed nonexistent ID (404); for a real record, test with a non-owner token (404).

### Test 21: Update one of my crops

**Method:** PATCH  
**URL:** `http://127.0.0.1:8000/crops/{{crop_id}}`  
**Authentication:** Required  
**Required role:** FARMER owner  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "quantity": 300,
  "growth_information": "Flowering"
}
```

**Expected HTTP status:** 200 OK

**Expected response:** `{"farm_id":"<string>","name":"<string>","planting_date":"2026-01-15","id":"<ObjectId>","owner_id":"<string>","is_active":true,"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Update one of my crops succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Try malformed ID → 422, nonexistent/other user’s resource → 404, or unauthenticated request → 401.

### Test 22: Deactivate one of my crops

**Method:** DELETE  
**URL:** `http://127.0.0.1:8000/crops/{{crop_id}}`  
**Authentication:** Required  
**Required role:** FARMER owner  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 204 No Content

**Expected response:** No body (204 No Content).

**What to verify:** Deactivate one of my crops succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Try malformed ID → 422, nonexistent/other user’s resource → 404, or unauthenticated request → 401.


## SECTION H: Marketplace

### Test 23: List produce for sale

**Method:** POST  
**URL:** `http://127.0.0.1:8000/marketplace/products`  
**Authentication:** Required  
**Required role:** FARMER (the listing is owned by the authenticated farmer)  
**Headers:**
```text
Content-Type: application/json
Authorization: Bearer FARMER_ACCESS_TOKEN
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "product_name": "White Maize",
  "category": "Grains",
  "description": "Dry, cleaned maize grains.",
  "quantity_available": 100,
  "unit": "kg",
  "price_per_unit_kes": 60,
  "county": "Kiambu",
  "sub_county": "Limuru",
  "product_images": []
}
```

**Expected HTTP status:** 201 Created

**Expected response:** `{"id":"<ObjectId>","farmer_id":"<farmer ObjectId>","product_name":"<string>","category":"<string>","description":"<string>","quantity_available":1,"unit":"<string>","price_per_unit_kes":100,"county":"<string>","sub_county":"<string>","product_images":["<string>"],"availability_status":"ACTIVE","created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** List produce for sale succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Copy product `id` to `product_id`; buyer uses it to place an order.

**Negative test:** Invalid/missing required JSON field or invalid enum/value → 422; use duplicate registration/bootstrap checks where applicable.

### Test 24: Browse available products

**Method:** GET  
**URL:** `http://127.0.0.1:8000/marketplace/products?limit=20&offset=0`  
**Authentication:** Not required  
**Required role:** Public  
**Headers:**
```text
None
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"items":[{"id":"<ObjectId>","farmer_id":"<farmer ObjectId>","product_name":"<string>","category":"<string>","description":"<string>","quantity_available":1,"unit":"<string>","price_per_unit_kes":100,"county":"<string>","sub_county":"<string>","product_images":["<string>"],"availability_status":"ACTIVE","created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}],"total":1,"limit":1,"offset":1}`

**What to verify:** Browse available products succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Copy product `id` to `product_id`; buyer uses it to place an order.

**Negative test:** Set `min_price_kes` above `max_price_kes`; the route returns 422. A search with no matches is a valid 200 with an empty `items` array.

### Test 25: List my product listings

**Method:** GET  
**URL:** `http://127.0.0.1:8000/marketplace/products/mine?limit=20&offset=0`  
**Authentication:** Required  
**Required role:** FARMER owner  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"items":[{"id":"<ObjectId>","farmer_id":"<farmer ObjectId>","product_name":"<string>","category":"<string>","description":"<string>","quantity_available":1,"unit":"<string>","price_per_unit_kes":100,"county":"<string>","sub_county":"<string>","product_images":["<string>"],"availability_status":"ACTIVE","created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}],"total":1,"limit":1,"offset":1}`

**What to verify:** List my product listings succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Try malformed ID → 422, nonexistent/other user’s resource → 404, or unauthenticated request → 401.

### Test 26: Get product details

**Method:** GET  
**URL:** `http://127.0.0.1:8000/marketplace/products/{{product_id}}`  
**Authentication:** Not required  
**Required role:** Public  
**Headers:**
```text
None
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"id":"<ObjectId>","farmer_id":"<farmer ObjectId>","product_name":"<string>","category":"<string>","description":"<string>","quantity_available":1,"unit":"<string>","price_per_unit_kes":100,"county":"<string>","sub_county":"<string>","product_images":["<string>"],"availability_status":"ACTIVE","created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Get product details succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Try a malformed ObjectId (422) and a well-formed nonexistent ID (404); for a real record, test with a non-owner token (404).

### Test 27: Update my product listing

**Method:** PATCH  
**URL:** `http://127.0.0.1:8000/marketplace/products/{{product_id}}`  
**Authentication:** Required  
**Required role:** FARMER owner  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "price_per_unit_kes": 65
}
```

**Expected HTTP status:** 200 OK

**Expected response:** `{"id":"<ObjectId>","farmer_id":"<farmer ObjectId>","product_name":"<string>","category":"<string>","description":"<string>","quantity_available":1,"unit":"<string>","price_per_unit_kes":100,"county":"<string>","sub_county":"<string>","product_images":["<string>"],"availability_status":"ACTIVE","created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Update my product listing succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Try malformed ID → 422, nonexistent/other user’s resource → 404, or unauthenticated request → 401.

### Test 28: Deactivate my product listing

**Method:** DELETE  
**URL:** `http://127.0.0.1:8000/marketplace/products/{{product_id}}`  
**Authentication:** Required  
**Required role:** FARMER owner  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 204 No Content

**Expected response:** No body (204 No Content).

**What to verify:** Deactivate my product listing succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Try malformed ID → 422, nonexistent/other user’s resource → 404, or unauthenticated request → 401.


## SECTION I: Orders

### Test 29: Place an order and reserve stock

**Method:** POST  
**URL:** `http://127.0.0.1:8000/orders`  
**Authentication:** Required  
**Required role:** BUYER  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "product_id": "{{product_id}}",
  "quantity": 2,
  "delivery_information": {
    "recipient_name": "Buyer One",
    "recipient_phone": "0712345678",
    "county": "Nairobi",
    "sub_county": "Westlands",
    "location": "Westlands, Nairobi",
    "instructions": "Call on arrival"
  }
}
```

**Expected HTTP status:** 201 Created

**Expected response:** `{"id":"<ObjectId>","buyer_id":"<buyer ObjectId>","seller_id":"<farmer ObjectId>","product_id":"<product ObjectId>","product_name":"<string>","quantity":2,"unit":"<string>","unit_price_kes":80,"total_amount_kes":160,"payment_id":null,"delivery_information":{"recipient_name":"Buyer One","recipient_phone":"0712345678","county":"Nairobi","sub_county":"Westlands","location":"Westlands, Nairobi","instructions":"Call on arrival"},"payment_status":"UNPAID","order_status":"AWAITING_PAYMENT","created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Place an order and reserve stock succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Copy order `id` to `order_id`; total and seller are calculated from stored product data.

**Negative test:** Insufficient stock or own product → 409; bad product ID/body → 422.

### Test 30: List my buyer orders

**Method:** GET  
**URL:** `http://127.0.0.1:8000/orders/buyer?limit=20&offset=0`  
**Authentication:** Required  
**Required role:** BUYER owner  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"items":[{"id":"<ObjectId>","buyer_id":"<buyer ObjectId>","seller_id":"<farmer ObjectId>","product_id":"<product ObjectId>","product_name":"<string>","quantity":1,"unit":"<string>","unit_price_kes":100,"total_amount_kes":100,"payment_id":null,"delivery_information":{"recipient_name":"<string>","recipient_phone":"<string>","county":"<string>","sub_county":"<string>","location":"<string>"},"payment_status":"UNPAID","order_status":"AWAITING_PAYMENT","created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}],"total":1,"limit":1,"offset":1}`

**What to verify:** List my buyer orders succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Try malformed ID → 422, nonexistent/other user’s resource → 404, or unauthenticated request → 401.

### Test 31: List orders for my products

**Method:** GET  
**URL:** `http://127.0.0.1:8000/orders/seller?limit=20&offset=0`  
**Authentication:** Required  
**Required role:** FARMER  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"items":[{"id":"<ObjectId>","buyer_id":"<buyer ObjectId>","seller_id":"<farmer ObjectId>","product_id":"<product ObjectId>","product_name":"<string>","quantity":1,"unit":"<string>","unit_price_kes":100,"total_amount_kes":100,"payment_id":null,"delivery_information":{"recipient_name":"<string>","recipient_phone":"<string>","county":"<string>","sub_county":"<string>","location":"<string>"},"payment_status":"UNPAID","order_status":"AWAITING_PAYMENT","created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}],"total":1,"limit":1,"offset":1}`

**What to verify:** List orders for my products succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

### Test 32: Get an order visible to me

**Method:** GET  
**URL:** `http://127.0.0.1:8000/orders/{{order_id}}`  
**Authentication:** Required  
**Required role:** Buyer, seller, or ADMIN (participant)  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"id":"<ObjectId>","buyer_id":"<buyer ObjectId>","seller_id":"<farmer ObjectId>","product_id":"<product ObjectId>","product_name":"<string>","quantity":1,"unit":"<string>","unit_price_kes":100,"total_amount_kes":100,"payment_id":null,"delivery_information":{"recipient_name":"<string>","recipient_phone":"<string>","county":"<string>","sub_county":"<string>","location":"<string>"},"payment_status":"UNPAID","order_status":"AWAITING_PAYMENT","created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Get an order visible to me succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Try a malformed ObjectId (422) and a well-formed nonexistent ID (404); for a real record, test with a non-owner token (404).

### Test 33: Cancel an unpaid order and release reserved stock

**Method:** POST  
**URL:** `http://127.0.0.1:8000/orders/{{order_id}}/cancel`  
**Authentication:** Required  
**Required role:** BUYER owner  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"id":"<ObjectId>","buyer_id":"<buyer ObjectId>","seller_id":"<farmer ObjectId>","product_id":"<product ObjectId>","product_name":"<string>","quantity":1,"unit":"<string>","unit_price_kes":100,"total_amount_kes":100,"payment_id":null,"delivery_information":{"recipient_name":"<string>","recipient_phone":"<string>","county":"<string>","sub_county":"<string>","location":"<string>"},"payment_status":"UNPAID","order_status":"CANCELLED","created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Cancel an unpaid order and release reserved stock succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Try malformed ID → 422, nonexistent/other user’s resource → 404, or unauthenticated request → 401.

### Test 34: Advance a paid seller order

**Method:** PATCH  
**URL:** `http://127.0.0.1:8000/orders/{{order_id}}/status`  
**Authentication:** Required  
**Required role:** FARMER seller  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "order_status": "PROCESSING"
}
```

**Expected HTTP status:** 200 OK

**Expected response:** `{"id":"<ObjectId>","buyer_id":"<buyer ObjectId>","seller_id":"<farmer ObjectId>","product_id":"<product ObjectId>","product_name":"<string>","quantity":1,"unit":"<string>","unit_price_kes":100,"total_amount_kes":100,"payment_id":"<payment ObjectId>","delivery_information":{"recipient_name":"<string>","recipient_phone":"<string>","county":"<string>","sub_county":"<string>","location":"<string>"},"payment_status":"PAID","order_status":"PROCESSING","created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Advance a paid seller order succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Sending `PAID` directly is rejected with 409; payment status can only change through verified payment processing. Try malformed ID → 422, another farmer’s order → 404, or unauthenticated request → 401.

State sequence: new order is `AWAITING_PAYMENT`/`UNPAID`; verified payment changes it to `PAID`; seller advances `PROCESSING` then `READY_FOR_DELIVERY`; delivery advances `PICKED_UP → IN_TRANSIT → DELIVERED`; buyer confirmation makes it `COMPLETED`. Seller cannot set `PAID`. Eligible unpaid cancellation releases reserved stock.


## SECTION J: M-Pesa and Payments

Mock callbacks simulate local status/ledger behavior only; they do not prove Safaricom integration. Real Daraja callbacks are provider-originated and verified by STK status query.

### Test 35: Initiate a payment for my unpaid order

**Method:** POST  
**URL:** `http://127.0.0.1:8000/payments/initiate`  
**Authentication:** Required  
**Required role:** BUYER owner  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
Idempotency-Key: unique-test-key-0001
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "order_id": "{{order_id}}",
  "phone_number": "0723456789"
}
```

**Expected HTTP status:** 201 Created

**Expected response:** `{"id":"<ObjectId>","order_id":"<order ObjectId>","buyer_id":"<buyer ObjectId>","provider":"<string>","status":"INITIATED","amount_kes":800,"currency":"KES","phone_number":"254723456789","merchant_reference":"<string>","created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Initiate a payment for my unpaid order succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Copy payment `id` to `payment_id`; mock local mode uses the mock callback.

**Negative test:** Missing Idempotency-Key → 422; other buyer’s order → 404; duplicate/ineligible payment → 409; provider unavailable → 503.

### Test 36: Daraja STK Push callback

**Method:** POST  
**URL:** `http://127.0.0.1:8000/payments/callback/daraja`  
**Authentication:** Not required  
**Required role:** Public provider callback  
**Headers:**
```text
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "Body": {
    "stkCallback": {}
  }
}
```

**Expected HTTP status:** 200 only for a verified provider callback; 400 malformed JSON, 409 conflicting callback, or 503 if transaction verification is unavailable/unconfirmed

**Expected response:** `{"accepted":true,"result_code":0,"result_description":"Payment verified"}`

**What to verify:** Daraja STK Push callback succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Malformed JSON → 400; unverified/mismatched callback → 503 or conflict → 409. Never fabricate a successful callback.

### Test 37: Development-only mock payment confirmation

**Method:** POST  
**URL:** `http://127.0.0.1:8000/payments/mock/{{payment_id}}/callback`  
**Authentication:** Required  
**Required role:** BUYER owner  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "success": true
}
```

**Expected HTTP status:** 200 OK

**Expected response:** `{"id":"<ObjectId>","order_id":"<order ObjectId>","buyer_id":"<buyer ObjectId>","provider":"mock","status":"SUCCEEDED","amount_kes":100,"currency":"KES","phone_number":"254723456789","merchant_reference":"<string>","created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z","provider_receipt":"MOCK-<receipt>"}`

**What to verify:** Development-only mock payment confirmation succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Check order/payment and then GET `/escrow/orders/{{order_id}}`; escrow is created by verified payment processing.

**Negative test:** Wrong amount or ineligible/duplicate callback → 409; wrong owner → 404; route disabled outside dev/test mock → 404.

### Test 38: List my payment history

**Method:** GET  
**URL:** `http://127.0.0.1:8000/payments/mine?limit=20&offset=0`  
**Authentication:** Required  
**Required role:** BUYER  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"items":[{"id":"<ObjectId>","order_id":"<order ObjectId>","buyer_id":"<buyer ObjectId>","provider":"<string>","status":"PENDING","amount_kes":100,"currency":"KES","phone_number":"254723456789","merchant_reference":"<string>","created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}],"total":1,"limit":1,"offset":1}`

**What to verify:** List my payment history succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

### Test 39: Get my payment

**Method:** GET  
**URL:** `http://127.0.0.1:8000/payments/{{payment_id}}`  
**Authentication:** Required  
**Required role:** Payment buyer or ADMIN  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"id":"<ObjectId>","order_id":"<order ObjectId>","buyer_id":"<buyer ObjectId>","provider":"<string>","status":"PENDING","amount_kes":100,"currency":"KES","phone_number":"254723456789","merchant_reference":"<string>","created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Get my payment succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Try a malformed ObjectId (422) and a well-formed nonexistent ID (404); for a real record, test with a non-owner token (404).

### Test 40: Query the configured provider without changing local payment/order status

**Method:** GET  
**URL:** `http://127.0.0.1:8000/payments/{{payment_id}}/provider-status`  
**Authentication:** Required  
**Required role:** Payment buyer or ADMIN  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"payment_id":"<payment ObjectId>","local_status":"INITIATED","provider_result":{},"payment_confirmed":false,"note":"Provider query does not mutate local status."}`

**What to verify:** Query the configured provider without changing local payment/order status succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Try a malformed ObjectId (422) and a well-formed nonexistent ID (404); for a real record, test with a non-owner token (404).

Mock flow: initiate under `PAYMENT_PROVIDER=mock`, then as the buyer call the mock callback with `{"success":true}`. Wrong amount returns 409; mock receipt/status are explicitly simulated. For real Daraja, use configured credentials and a publicly reachable callback; never submit made-up success data.


## SECTION K: Escrow

The application records an internal escrow-style workflow; this is not a claim that the platform legally holds funds. Mock escrow never safeguards or transfers money.

### Test 41: Get escrow status by order ID

**Method:** GET  
**URL:** `http://127.0.0.1:8000/escrow/orders/{{order_id}}`  
**Authentication:** Required  
**Required role:** Order buyer, seller, or ADMIN  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"id":"<ObjectId>","order_id":"<order ObjectId>","payment_id":"<payment ObjectId>","provider":"<string>","status":"PAYMENT_RECEIVED","custody_status":"NOT_SAFEGUARDED","actual_funds_safeguarded":false,"amount_kes":100,"commission_kes":100,"seller_amount_kes":100,"provider_reference":null,"last_action_reference":null,"refund_reason":null,"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Get escrow status by order ID succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Try a malformed ObjectId (422) and a well-formed nonexistent ID (404); for a real record, test with a non-owner token (404).

### Test 42: Get escrow workflow and actual custody status

**Method:** GET  
**URL:** `http://127.0.0.1:8000/escrow/{{escrow_id}}`  
**Authentication:** Required  
**Required role:** Order buyer, seller, or ADMIN  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"id":"<ObjectId>","order_id":"<order ObjectId>","payment_id":"<payment ObjectId>","provider":"<string>","status":"PAYMENT_RECEIVED","custody_status":"NOT_SAFEGUARDED","actual_funds_safeguarded":false,"amount_kes":100,"commission_kes":100,"seller_amount_kes":100,"provider_reference":null,"last_action_reference":null,"refund_reason":null,"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Get escrow workflow and actual custody status succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Try a malformed ObjectId (422) and a well-formed nonexistent ID (404); for a real record, test with a non-owner token (404).

### Test 43: Request seller settlement after delivery confirmation

**Method:** POST  
**URL:** `http://127.0.0.1:8000/escrow/{{escrow_id}}/release`  
**Authentication:** Required  
**Required role:** FARMER seller or ADMIN  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"status":"SIMULATED_SETTLEMENT","message":"<string>","escrow":{"id":"<ObjectId>","order_id":"<order ObjectId>","payment_id":"<payment ObjectId>","provider":"<string>","status":"SIMULATED_SETTLEMENT","custody_status":"NOT_SAFEGUARDED","actual_funds_safeguarded":false,"amount_kes":100,"commission_kes":100,"seller_amount_kes":100,"provider_reference":null,"last_action_reference":"<mock provider reference>","refund_reason":null,"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}}`

**What to verify:** Request seller settlement after delivery confirmation succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Open dispute or unconfirmed delivery → 409; mock release outside development/test → 503.

### Test 44: Request a refund review for a buyer order

**Method:** POST  
**URL:** `http://127.0.0.1:8000/escrow/{{escrow_id}}/refund-request`  
**Authentication:** Required  
**Required role:** BUYER owner  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "reason": "Please review this order payment and advise on refund eligibility."
}
```

**Expected HTTP status:** 200 OK

**Expected response:** `{"status":"<string>","message":"<string>","escrow":{"id":"<ObjectId>","order_id":"<order ObjectId>","payment_id":"<payment ObjectId>","provider":"<string>","status":"REFUND_REQUESTED","custody_status":"NOT_SAFEGUARDED","actual_funds_safeguarded":false,"amount_kes":100,"commission_kes":100,"seller_amount_kes":100,"provider_reference":null,"last_action_reference":null,"refund_reason":"Please review this order payment and advise on refund eligibility.","created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}}`

**What to verify:** Request a refund review for a buyer order succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Wrong role → 403; a short reason or invalid body → 422; refund requested after completed order or settlement → 409.

### Test 45: View append-only financial events for an order

**Method:** GET  
**URL:** `http://127.0.0.1:8000/transactions/orders/{{order_id}}/ledger`  
**Authentication:** Required  
**Required role:** Order buyer, seller, or ADMIN  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"items":[{"id":"<ObjectId>","order_id":"<order ObjectId>","event_type":"PAYMENT_RECEIVED","amount_kes":100,"currency":"KES","timestamp":"2026-01-15T09:00:00Z","status":"<string>"}],"total":1}`

**What to verify:** View append-only financial events for an order succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Try a malformed ObjectId (422) and a well-formed nonexistent ID (404); for a real record, test with a non-owner token (404).

### Test 46: View payout and escrow status

**Method:** GET  
**URL:** `http://127.0.0.1:8000/payouts/{{escrow_id}}`  
**Authentication:** Required  
**Required role:** Order buyer, seller, or ADMIN  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"id":"<ObjectId>","order_id":"<order ObjectId>","payment_id":"<payment ObjectId>","provider":"<string>","status":"PAYMENT_RECEIVED","custody_status":"NOT_SAFEGUARDED","actual_funds_safeguarded":false,"amount_kes":100,"commission_kes":100,"seller_amount_kes":100,"provider_reference":null,"last_action_reference":null,"refund_reason":null,"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** View payout and escrow status succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Try a malformed ObjectId (422) and a well-formed nonexistent ID (404); for a real record, test with a non-owner token (404).

### Test 47: Request payout after delivery confirmation

**Method:** POST  
**URL:** `http://127.0.0.1:8000/payouts/{{escrow_id}}/release`  
**Authentication:** Required  
**Required role:** FARMER seller or ADMIN  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"status":"SIMULATED_SETTLEMENT","message":"<string>","escrow":{"id":"<ObjectId>","order_id":"<order ObjectId>","payment_id":"<payment ObjectId>","provider":"<string>","status":"SIMULATED_SETTLEMENT","custody_status":"NOT_SAFEGUARDED","actual_funds_safeguarded":false,"amount_kes":100,"commission_kes":100,"seller_amount_kes":100,"provider_reference":null,"last_action_reference":"<mock provider reference>","refund_reason":null,"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}}`

**What to verify:** Request payout after delivery confirmation succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Open dispute or incomplete delivery → 409; duplicate mock release is idempotent.

Buyer delivery confirmation is required before release; an unresolved dispute blocks release. Mock response may be `SIMULATED_SETTLEMENT`, with `actual_funds_safeguarded=false`; repeat release must not create another payout ledger event. Mock refund request only records workflow. Commission defaults to 500 basis points (5%); money is integer KES.


## SECTION L: Deliveries

### Test 48: Create delivery details for a seller order

**Method:** POST  
**URL:** `http://127.0.0.1:8000/deliveries/orders/{{order_id}}`  
**Authentication:** Required  
**Required role:** FARMER seller  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "carrier_name": "Local courier",
  "carrier_phone": "0712345678",
  "tracking_reference": "TEST-TRACK-001"
}
```

**Expected HTTP status:** 201 Created

**Expected response:** `{"id":"<ObjectId>","order_id":"<order ObjectId>","buyer_id":"<buyer ObjectId>","seller_id":"<farmer ObjectId>","status":"PENDING","events":[{}],"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Create delivery details for a seller order succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Copy delivery `id` to `delivery_id`; advance statuses in order.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

### Test 49: List deliveries for the current buyer or farmer

**Method:** GET  
**URL:** `http://127.0.0.1:8000/deliveries/mine?limit=20&offset=0`  
**Authentication:** Required  
**Required role:** BUYER or FARMER  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"items":[{"id":"<ObjectId>","order_id":"<order ObjectId>","buyer_id":"<buyer ObjectId>","seller_id":"<farmer ObjectId>","status":"PENDING","events":[{}],"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}],"total":1,"limit":1,"offset":1}`

**What to verify:** List deliveries for the current buyer or farmer succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

### Test 50: Get delivery tracking details

**Method:** GET  
**URL:** `http://127.0.0.1:8000/deliveries/{{delivery_id}}`  
**Authentication:** Required  
**Required role:** Buyer, seller, or ADMIN  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"id":"<ObjectId>","order_id":"<order ObjectId>","buyer_id":"<buyer ObjectId>","seller_id":"<farmer ObjectId>","status":"PENDING","events":[{}],"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Get delivery tracking details succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Try a malformed ObjectId (422) and a well-formed nonexistent ID (404); for a real record, test with a non-owner token (404).

### Test 51: Seller or admin updates delivery progress

**Method:** PATCH  
**URL:** `http://127.0.0.1:8000/deliveries/{{delivery_id}}/status`  
**Authentication:** Required  
**Required role:** FARMER seller or ADMIN  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "status": "PICKED_UP",
  "note": "Collected from farm"
}
```

**Expected HTTP status:** 200 OK

**Expected response:** `{"id":"<ObjectId>","order_id":"<order ObjectId>","buyer_id":"<buyer ObjectId>","seller_id":"<farmer ObjectId>","status":"PENDING","events":[{}],"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Seller or admin updates delivery progress succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

### Test 52: Buyer confirms receipt and completes the order

**Method:** POST  
**URL:** `http://127.0.0.1:8000/deliveries/{{delivery_id}}/confirm`  
**Authentication:** Required  
**Required role:** BUYER owner  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"id":"<ObjectId>","order_id":"<order ObjectId>","buyer_id":"<buyer ObjectId>","seller_id":"<farmer ObjectId>","status":"PENDING","events":[{}],"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Buyer confirms receipt and completes the order succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Try malformed ID → 422, nonexistent/other user’s resource → 404, or unauthenticated request → 401.


## SECTION M: Disputes

### Test 53: Open a dispute for a paid order

**Method:** POST  
**URL:** `http://127.0.0.1:8000/disputes`  
**Authentication:** Required  
**Required role:** BUYER or FARMER  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "order_id": "{{order_id}}",
  "reason": "DAMAGED_PRODUCE",
  "description": "The produce arrived damaged and requires review.",
  "evidence_urls": []
}
```

**Expected HTTP status:** 201 Created

**Expected response:** `{"id":"<ObjectId>","order_id":"<order ObjectId>","buyer_id":"<buyer ObjectId>","seller_id":"<farmer ObjectId>","raised_by":"<string>","reason":"PRODUCT_NOT_DELIVERED","description":"<string>","evidence_urls":["<string>"],"status":"OPEN","decisions":[{}],"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Open a dispute for a paid order succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Copy dispute `id` to `dispute_id`; use it in admin review.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

### Test 54: List disputes for the current farmer or buyer

**Method:** GET  
**URL:** `http://127.0.0.1:8000/disputes/mine?limit=20&offset=0`  
**Authentication:** Required  
**Required role:** BUYER or FARMER  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"items":[{"id":"<ObjectId>","order_id":"<order ObjectId>","buyer_id":"<buyer ObjectId>","seller_id":"<farmer ObjectId>","raised_by":"<string>","reason":"PRODUCT_NOT_DELIVERED","description":"<string>","evidence_urls":["<string>"],"status":"OPEN","decisions":[{}],"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}],"total":1,"limit":1,"offset":1}`

**What to verify:** List disputes for the current farmer or buyer succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

### Test 55: Get a dispute visible to its participants or admin

**Method:** GET  
**URL:** `http://127.0.0.1:8000/disputes/{{dispute_id}}`  
**Authentication:** Required  
**Required role:** Participant or ADMIN  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"id":"<ObjectId>","order_id":"<order ObjectId>","buyer_id":"<buyer ObjectId>","seller_id":"<farmer ObjectId>","raised_by":"<string>","reason":"PRODUCT_NOT_DELIVERED","description":"<string>","evidence_urls":["<string>"],"status":"OPEN","decisions":[{}],"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Get a dispute visible to its participants or admin succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Try a malformed ObjectId (422) and a well-formed nonexistent ID (404); for a real record, test with a non-owner token (404).

Valid admin path: `OPEN → UNDER_REVIEW → RESOLVED` or `REJECTED`; only resolved/rejected disputes can be closed. A final decision is required for RESOLVED/REJECTED and is stored in `decisions`. Use a separate paid order from normal payout testing.


## SECTION N: Weather

### Test 56: Get current weather and five-day forecast for coordinates

**Method:** GET  
**URL:** `http://127.0.0.1:8000/weather/forecast?latitude=-0.3031&longitude=36.0800`  
**Authentication:** Required  
**Required role:** FARMER, AGRICULTURAL_OFFICER, or ADMIN  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK; 503 if weather key/provider is unavailable

**Expected response:** `{"latitude":1.0,"longitude":1.0,"source":"<string>","retrieved_at":"2026-01-15T09:00:00Z","current":{"observed_at":"2026-01-15T09:00:00Z","temperature_c":1.0,"rainfall_mm":1.0,"humidity_percent":1,"conditions":"<string>"},"forecast":[{"forecast_at":"2026-01-15T09:00:00Z","temperature_c":1.0,"rainfall_mm":1.0,"humidity_percent":1,"conditions":"<string>"}]}`

**What to verify:** Get current weather and five-day forecast for coordinates succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Invalid coordinates → 422; missing key or provider error → 503.


## SECTION O: Agricultural Advisory

### Test 57: Create an officer-authored agricultural advisory

**Method:** POST  
**URL:** `http://127.0.0.1:8000/advisories`  
**Authentication:** Required  
**Required role:** FARMER, AGRICULTURAL_OFFICER, or ADMIN  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "title": "County planting information",
  "message": "Contact your county agricultural extension officer for current, location-specific planting dates and crop guidance.",
  "crop_name": "Maize",
  "county": "Nakuru",
  "source_name": "Local Postman test sample"
}
```

**Expected HTTP status:** 201 Created

**Expected response:** `{"id":"<ObjectId>","kind":"OFFICER","title":"<string>","message":"<string>","source_name":"<string>","is_active":true,"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Create an officer-authored agricultural advisory succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

### Test 58: List relevant advisories and my weather recommendation history

**Method:** GET  
**URL:** `http://127.0.0.1:8000/advisories?crop_name=Maize&county=Nakuru&limit=20`  
**Authentication:** Required  
**Required role:** FARMER, AGRICULTURAL_OFFICER, or ADMIN  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"items":[{"id":"<ObjectId>","kind":"OFFICER","title":"<string>","message":"<string>","source_name":"<string>","is_active":true,"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}],"total":1,"limit":1,"offset":1}`

**What to verify:** List relevant advisories and my weather recommendation history succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

### Test 59: List my farm-linked weather recommendation history

**Method:** GET  
**URL:** `http://127.0.0.1:8000/advisories/mine?limit=20&offset=0`  
**Authentication:** Required  
**Required role:** FARMER  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"items":[{"id":"<ObjectId>","kind":"OFFICER","title":"<string>","message":"<string>","source_name":"<string>","is_active":true,"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}],"total":1,"limit":1,"offset":1}`

**What to verify:** List my farm-linked weather recommendation history succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

### Test 60: Create and store a crop-linked weather rule recommendation

**Method:** POST  
**URL:** `http://127.0.0.1:8000/advisories/recommendations/weather`  
**Authentication:** Required  
**Required role:** FARMER  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "farm_id": "{{farm_id}}",
  "crop_id": "{{crop_id}}",
  "latitude": "-0.3031",
  "longitude": "36.0800"
}
```

**Expected HTTP status:** 201 Created; 503 if weather provider is unavailable

**Expected response:** `{"id":"<ObjectId>","kind":"OFFICER","title":"<string>","message":"<string>","source_name":"<string>","is_active":true,"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Create and store a crop-linked weather rule recommendation succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Unowned farm/crop → 404; missing weather key/provider error → 503; invalid coordinates → 422.

### Test 61: Update or deactivate an officer advisory

**Method:** PATCH  
**URL:** `http://127.0.0.1:8000/advisories/{{advisory_id}}`  
**Authentication:** Required  
**Required role:** Authoring AGRICULTURAL_OFFICER or ADMIN  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "is_active": false
}
```

**Expected HTTP status:** 200 OK

**Expected response:** `{"id":"<ObjectId>","kind":"OFFICER","title":"<string>","message":"<string>","source_name":"<string>","is_active":true,"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Update or deactivate an officer advisory succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.


## SECTION P: Market Prices

### Test 62: Record an observed market price

**Method:** POST  
**URL:** `http://127.0.0.1:8000/market-prices`  
**Authentication:** Required  
**Required role:** AGRICULTURAL_OFFICER or ADMIN  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "crop_name": "Maize",
  "market_location": "Test market (not a real quote)",
  "county": "Nakuru",
  "price_kes": "100",
  "unit": "kg",
  "date_collected": "2026-01-15",
  "data_source": "MANUAL",
  "source_name": "Synthetic test record; not a current market quote"
}
```

**Expected HTTP status:** 201 Created

**Expected response:** `{"id":"<ObjectId>","crop_name":"<string>","market_location":"<string>","county":"<string>","price_kes":100,"unit":"<string>","date_collected":"2026-01-15","data_source":"MANUAL","source_name":"<string>","recorded_by":"<string>","created_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Record an observed market price succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Copy returned `id` to `price_id` for a correction revision.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

### Test 63: List price observations with filters

**Method:** GET  
**URL:** `http://127.0.0.1:8000/market-prices?crop_name=Maize&county=Nakuru&limit=20&offset=0`  
**Authentication:** Required  
**Required role:** Any authenticated user  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"items":[{"id":"<ObjectId>","crop_name":"<string>","market_location":"<string>","county":"<string>","price_kes":100,"unit":"<string>","date_collected":"2026-01-15","data_source":"MANUAL","source_name":"<string>","recorded_by":"<string>","created_at":"2026-01-15T09:00:00Z"}],"total":1,"limit":1,"offset":1}`

**What to verify:** List price observations with filters succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Copy returned `id` to `price_id` for a correction revision.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

### Test 64: Compare the latest recorded price at each market

**Method:** GET  
**URL:** `http://127.0.0.1:8000/market-prices/compare?crop_name=Maize&county=Nakuru`  
**Authentication:** Required  
**Required role:** Any authenticated user  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"crop_name":"<string>","county":"<string>","items":[{"id":"<ObjectId>","crop_name":"<string>","market_location":"<string>","county":"<string>","price_kes":100,"unit":"<string>","date_collected":"2026-01-15","data_source":"MANUAL","source_name":"<string>","recorded_by":"<string>","created_at":"2026-01-15T09:00:00Z"}]}`

**What to verify:** Compare the latest recorded price at each market succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

### Test 65: Retrieve historical observations for a crop

**Method:** GET  
**URL:** `http://127.0.0.1:8000/market-prices/history?crop_name=Maize&county=Nakuru&limit=100`  
**Authentication:** Required  
**Required role:** Any authenticated user  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"items":[{"id":"<ObjectId>","crop_name":"<string>","market_location":"<string>","county":"<string>","price_kes":100,"unit":"<string>","date_collected":"2026-01-15","data_source":"MANUAL","source_name":"<string>","recorded_by":"<string>","created_at":"2026-01-15T09:00:00Z"}],"total":1,"limit":1,"offset":1}`

**What to verify:** Retrieve historical observations for a crop succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

### Test 66: Add a corrected observation without erasing history

**Method:** POST  
**URL:** `http://127.0.0.1:8000/market-prices/{{price_id}}/revision`  
**Authentication:** Required  
**Required role:** AGRICULTURAL_OFFICER or ADMIN  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "price_kes": "100",
  "date_collected": "2026-01-15",
  "source_name": "Synthetic test record; not a current market quote"
}
```

**Expected HTTP status:** 201 Created

**Expected response:** `{"id":"<ObjectId>","crop_name":"<string>","market_location":"<string>","county":"<string>","price_kes":100,"unit":"<string>","date_collected":"2026-01-15","data_source":"MANUAL","source_name":"<string>","recorded_by":"<string>","created_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Add a corrected observation without erasing history succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.


## SECTION Q: Crop Disease Detection

No trained model or label file is bundled. Until a compatible Keras model, label map, and runtime are configured, HTTP 503 is the correct unavailable result—not a successful prediction.

### Test 67: Upload a crop image for model-based disease screening

**Method:** POST  
**URL:** `http://127.0.0.1:8000/disease-detection/predict`  
**Authentication:** Required  
**Required role:** FARMER  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

Choose **Body → form-data**; key `image`, type **File**, select JPEG/PNG/WebP. Do not set Content-Type manually; Postman must create the multipart boundary.

**Expected HTTP status:** 201 Created; 503 if model/labels/runtime are unavailable

**Expected response:** `{"id":"<ObjectId>","farmer_id":"<farmer ObjectId>","filename":"tomato-leaf.jpg","content_type":"<string>","file_size_bytes":1,"image_sha256":"<string>","predicted_label":"model class label","confidence":1.0,"disclaimer":"AI model output is a preliminary screening result, not a guaranteed diagnosis. Ask an agricultural officer to assess uncertain or serious cases.","created_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Upload a crop image for model-based disease screening succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** On 201, save `id` and check own history; on 503, configure model/labels first.

**Negative test:** No file → 422; unsupported MIME → 415; corrupt image → 422; over size limit → 413; no trained model/labels → 503.

### Test 68: List the authenticated farmer's disease screening history

**Method:** GET  
**URL:** `http://127.0.0.1:8000/disease-detection/mine?limit=20&offset=0`  
**Authentication:** Required  
**Required role:** FARMER; own history  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"items":[{"id":"<ObjectId>","farmer_id":"<farmer ObjectId>","filename":"tomato-leaf.jpg","content_type":"<string>","file_size_bytes":1,"image_sha256":"<string>","predicted_label":"model class label","confidence":1.0,"disclaimer":"AI model output is a preliminary screening result, not a guaranteed diagnosis. Ask an agricultural officer to assess uncertain or serious cases.","created_at":"2026-01-15T09:00:00Z"}],"total":1,"limit":1,"offset":1}`

**What to verify:** List the authenticated farmer's disease screening history succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

Image rules: JPEG/PNG/WebP only; default file maximum 8 MiB and image dimensions at most 25 million pixels. Invalid MIME gives 415, corrupt/empty gives 422, oversize gives 413. Original image bytes are not saved; successful prediction metadata/hash is. Confidence is not a guaranteed diagnosis.


## SECTION R: Notifications and SMS

Local `SMS_PROVIDER=mock` returns a simulation and sends nothing. Africa’s Talking Sandbox writes to its simulator only; provider `ACCEPTED` in production does not prove handset delivery.

### Test 69: List my in-app notification and SMS attempt history

**Method:** GET  
**URL:** `http://127.0.0.1:8000/notifications/mine?limit=20&offset=0`  
**Authentication:** Required  
**Required role:** Any authenticated user; own history  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"items":[{"id":"<ObjectId>","recipient_user_id":"<string>","event":"REGISTRATION","message":"<string>","provider":"<string>","status":"PENDING","created_at":"2026-01-15T09:00:00Z"}],"total":1,"limit":1,"offset":1}`

**What to verify:** List my in-app notification and SMS attempt history succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

### Test 70: Send an event SMS to a registered user (admin/officer operation)

**Method:** POST  
**URL:** `http://127.0.0.1:8000/notifications/send`  
**Authentication:** Required  
**Required role:** AGRICULTURAL_OFFICER or ADMIN  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
Idempotency-Key: unique-test-key-0001
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "recipient_user_id": "{{buyer_id}}",
  "event": "NEW_ORDER",
  "message": "A new order update is available in your Smart Agriculture account."
}
```

**Expected HTTP status:** 200 OK; 502 if SMS provider fails

**Expected response:** `{"notification":{"id":"<ObjectId>","recipient_user_id":"<string>","event":"REGISTRATION","message":"<string>","provider":"<string>","status":"SIMULATED","created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"},"detail":"<string>"}`

**What to verify:** Send an event SMS to a registered user (admin/officer operation) succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Missing/short idempotency header or invalid payload → 422; unknown user → 404; provider error → 502.


## SECTION S: Administration

Implemented admin endpoints are collected here. There are no separate admin CRUD routes for every resource, no statistics/report endpoint, and no dashboard endpoint. Admin can read selected participant resources only where their route allows it. Passwords are never returned.

### Test 71: Create an administrator or agricultural officer account

**Method:** POST  
**URL:** `http://127.0.0.1:8000/auth/admin/users`  
**Authentication:** Required  
**Required role:** ADMIN  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "full_name": "Test Agriculture Officer",
  "email": "officer1@example.com",
  "phone": "0745678901",
  "password": "LocalTestPass!234",
  "role": "AGRICULTURAL_OFFICER"
}
```

**Expected HTTP status:** 201 Created

**Expected response:** `{"id":"<ObjectId>","full_name":"Test Agriculture Officer","email":"officer1@example.com","phone":"+254745678901","role":"AGRICULTURAL_OFFICER","is_active":true,"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Create an administrator or agricultural officer account succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

### Test 72: List user accounts (administrator only)

**Method:** GET  
**URL:** `http://127.0.0.1:8000/auth/admin/users?limit=20&offset=0`  
**Authentication:** Required  
**Required role:** ADMIN  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"items":[{"id":"<ObjectId>","full_name":"Test Agriculture Officer","email":"officer1@example.com","phone":"+254745678901","role":"AGRICULTURAL_OFFICER","is_active":true,"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}],"total":1,"limit":1,"offset":1}`

**What to verify:** List user accounts (administrator only) succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

### Test 73: List platform payment history

**Method:** GET  
**URL:** `http://127.0.0.1:8000/payments/admin/history?limit=20&offset=0`  
**Authentication:** Required  
**Required role:** ADMIN  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"items":[{"id":"<ObjectId>","order_id":"<order ObjectId>","buyer_id":"<buyer ObjectId>","provider":"<string>","status":"PENDING","amount_kes":100,"currency":"KES","phone_number":"254723456789","merchant_reference":"<string>","created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}],"total":1,"limit":1,"offset":1}`

**What to verify:** List platform payment history succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

### Test 74: Admin list of disputes

**Method:** GET  
**URL:** `http://127.0.0.1:8000/disputes?limit=20&offset=0`  
**Authentication:** Required  
**Required role:** ADMIN  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Body:**

No request body; choose **Body → none**.

**Expected HTTP status:** 200 OK

**Expected response:** `{"items":[{"id":"<ObjectId>","order_id":"<order ObjectId>","buyer_id":"<buyer ObjectId>","seller_id":"<farmer ObjectId>","raised_by":"<string>","reason":"PRODUCT_NOT_DELIVERED","description":"<string>","evidence_urls":["<string>"],"status":"OPEN","decisions":[{}],"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}],"total":1,"limit":1,"offset":1,"status":"OPEN"}`

**What to verify:** Admin list of disputes succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Copy dispute `id` to `dispute_id`; use it in admin review.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

### Test 75: Record an audited administrator dispute decision

**Method:** PATCH  
**URL:** `http://127.0.0.1:8000/disputes/{{dispute_id}}/review`  
**Authentication:** Required  
**Required role:** ADMIN  
**Headers:**
```text
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

**Body:**

Choose **Body → raw → JSON**:

```json
{
  "status": "UNDER_REVIEW",
  "resolution": "Reviewing submitted evidence and the other participant response."
}
```

**Expected HTTP status:** 200 OK

**Expected response:** `{"id":"<ObjectId>","order_id":"<order ObjectId>","buyer_id":"<buyer ObjectId>","seller_id":"<farmer ObjectId>","raised_by":"<string>","reason":"PRODUCT_NOT_DELIVERED","description":"<string>","evidence_urls":["<string>"],"status":"UNDER_REVIEW","decisions":[{}],"created_at":"2026-01-15T09:00:00Z","updated_at":"2026-01-15T09:00:00Z"}`

**What to verify:** Record an audited administrator dispute decision succeeds only with valid inputs and the listed access. Confirm the status and response fields; paginated responses use `items`, `total`, `limit`, and `offset`.

**Next step:** Use the returned `id` for the next related request; for lists, choose an actual `items[n].id`.

**Negative test:** Remove Authorization → 401; use a logged-in account with the wrong role → 403; invalid input/query → 422.

These are all admin-only endpoints registered by this application: managed-user create/list, platform payment history, dispute list and dispute review. No admin reports/statistics endpoint is registered.


## Manual workflow checklist

1. Health liveness/readiness. 2. Farmer register/login → farmer profile → farm → crop → listing. 3. Buyer register/login → buyer profile → browse → order. 4. Confirm mock payment configuration → initiate → mock callback → inspect payment, order, escrow and ledger. 5. Seller processing/ready → create delivery → picked up/in transit/delivered → buyer confirms → seller requests simulated payout. 6. Use a separate paid order for dispute creation/review/resolution and verify release protection. 7. Admin bootstrap once → login → create officer → admin user/payment/dispute requests. 8. Weather requires external key; SMS mock/sandbox only; disease prediction requires trained model. Send each request manually; do not run the collection automatically.

## Database verification in MongoDB Atlas

Use `DATABASE_NAME` in Atlas Data Explorer. Never share connection strings or credentials. Collections/references in the current repositories:

| Collection | Key fields / relationship |
|---|---|
| `users` | role, normalized email/phone, active/timestamps; password hash is private; `_id` root |
| `farmers`, `buyers` | `user_id → users._id`; profile attributes |
| `farms` | `owner_id → users._id`; county/location/size/soil/active |
| `crops` | `farm_id → farms._id`, owner; planting/harvest/quantity/growth |
| `marketplace_products` | `farmer_id → users._id`; price/stock/availability/images URLs |
| `orders` | buyer/seller/product references, quantity, price snapshot, delivery data and statuses |
| `payments` | `order_id`, buyer/provider/status/amount/phone/receipt |
| `escrow_transactions` | order/payment, custody/workflow state, integer commission/seller amounts, payout/refund state |
| `transaction_ledger` | append-only order/payment event, amount, provider reference/status/timestamp |
| `deliveries` | order/buyer/seller, current status and timestamped events |
| `disputes` | order/buyer/seller, reason/status, evidence URLs, decision audit |
| `advisories` | officer/weather-rule text, sources, optional farm/crop/farmer references |
| `market_prices` | crop/county/market, integer KES/date/source, `supersedes_id` |
| `notifications` | recipient/event/message/provider/status; public API omits recipient phone/idempotency key |
| `disease_reports` | farmer, file metadata/hash, predicted class/confidence/disclaimer; original image omitted |

There is no `payouts` collection; payout status is on `escrow_transactions` and ledger events are in `transaction_ledger`. Weather snapshots are held in `advisories`. Confirm manual writes in the test database; automated tests use in-memory repositories and do not prove Atlas persistence.

## Integration limits and routes not implemented

- MongoDB Atlas must be reachable and allow the client IP. Database errors generally return 503.
- Weather forecast/recommendation calls OpenWeatherMap and needs `WEATHER_API_KEY`; provider failure/missing key returns 503.
- Daraja STK initiation/status requires Safaricom credentials; callbacks need a publicly reachable callback URL and provider query verification. Real integration tests require actual sandbox transactions.
- Mock payment callback works only when `APP_ENV=development` or `test` and `PAYMENT_PROVIDER=mock`; it is not a real M-Pesa payment.
- Mock escrow simulates only. The `partner` adapter fails closed until an authorised safeguarded-funds provider is integrated. Real payout/refund/custody requires partner integration tests.
- Africa’s Talking Sandbox requires its sandbox API key and `SMS_USERNAME=sandbox`; simulator records do not reach a phone. `ACCEPTED` does not confirm handset delivery.
- Disease inference requires TensorFlow, a trusted `.keras` model and matching JSON class labels. These assets are not bundled; 503 is expected until configured.
- Not implemented: password reset/change; evidence file hosting (disputes accept URLs); image file hosting for marketplace listings (they hold URL strings); admin dashboard/statistics; dedicated admin CRUD for every resource; and a separate payouts collection. No endpoint should be invented for these.

## API coverage report

All 75 registered HTTP method/path combinations appear below. Different methods on the same path are separate rows. Every manual test begins as **NOT TESTED**; change this only after sending it yourself in Postman.

| No. | HTTP Method | Endpoint | Module | Authentication | Required Role | Manual Test Status |
|---:|---|---|---|---|---|---|
| 1 | GET | `/advisories` | Agricultural Advisory | Yes | FARMER, AGRICULTURAL_OFFICER, or ADMIN | NOT TESTED |
| 2 | POST | `/advisories` | Agricultural Advisory | Yes | FARMER, AGRICULTURAL_OFFICER, or ADMIN | NOT TESTED |
| 3 | GET | `/advisories/mine` | Agricultural Advisory | Yes | FARMER | NOT TESTED |
| 4 | POST | `/advisories/recommendations/weather` | Agricultural Advisory | Yes | FARMER | NOT TESTED |
| 5 | PATCH | `/advisories/{advisory_id}` | Agricultural Advisory | Yes | Authoring AGRICULTURAL_OFFICER or ADMIN | NOT TESTED |
| 6 | GET | `/auth/admin/users` | Authentication | Yes | ADMIN | NOT TESTED |
| 7 | POST | `/auth/admin/users` | Authentication | Yes | ADMIN | NOT TESTED |
| 8 | POST | `/auth/bootstrap-admin` | Authentication | No | Public + X-Admin-Bootstrap-Token | NOT TESTED |
| 9 | POST | `/auth/login` | Authentication | No | Public | NOT TESTED |
| 10 | GET | `/auth/me` | Authentication | Yes | Any authenticated user | NOT TESTED |
| 11 | PATCH | `/auth/me` | Authentication | Yes | Any authenticated user | NOT TESTED |
| 12 | POST | `/auth/register/buyer` | Authentication | No | Public | NOT TESTED |
| 13 | POST | `/auth/register/farmer` | Authentication | No | Public | NOT TESTED |
| 14 | GET | `/buyers/me` | Buyers | Yes | BUYER | NOT TESTED |
| 15 | PUT | `/buyers/me` | Buyers | Yes | BUYER | NOT TESTED |
| 16 | GET | `/crops` | Crops | Yes | FARMER | NOT TESTED |
| 17 | POST | `/crops` | Crops | Yes | FARMER | NOT TESTED |
| 18 | DELETE | `/crops/{crop_id}` | Crops | Yes | FARMER owner | NOT TESTED |
| 19 | GET | `/crops/{crop_id}` | Crops | Yes | FARMER owner | NOT TESTED |
| 20 | PATCH | `/crops/{crop_id}` | Crops | Yes | FARMER owner | NOT TESTED |
| 21 | GET | `/deliveries/mine` | Deliveries | Yes | BUYER or FARMER | NOT TESTED |
| 22 | POST | `/deliveries/orders/{order_id}` | Deliveries | Yes | FARMER seller | NOT TESTED |
| 23 | GET | `/deliveries/{delivery_id}` | Deliveries | Yes | Buyer, seller, or ADMIN | NOT TESTED |
| 24 | POST | `/deliveries/{delivery_id}/confirm` | Deliveries | Yes | BUYER owner | NOT TESTED |
| 25 | PATCH | `/deliveries/{delivery_id}/status` | Deliveries | Yes | FARMER seller or ADMIN | NOT TESTED |
| 26 | GET | `/disease-detection/mine` | Disease Detection | Yes | FARMER; own history | NOT TESTED |
| 27 | POST | `/disease-detection/predict` | Disease Detection | Yes | FARMER | NOT TESTED |
| 28 | GET | `/disputes` | Disputes | Yes | ADMIN | NOT TESTED |
| 29 | POST | `/disputes` | Disputes | Yes | BUYER or FARMER | NOT TESTED |
| 30 | GET | `/disputes/mine` | Disputes | Yes | BUYER or FARMER | NOT TESTED |
| 31 | GET | `/disputes/{dispute_id}` | Disputes | Yes | Participant or ADMIN | NOT TESTED |
| 32 | PATCH | `/disputes/{dispute_id}/review` | Disputes | Yes | ADMIN | NOT TESTED |
| 33 | GET | `/escrow/orders/{order_id}` | Escrow | Yes | Order buyer, seller, or ADMIN | NOT TESTED |
| 34 | GET | `/escrow/{escrow_id}` | Escrow | Yes | Order buyer, seller, or ADMIN | NOT TESTED |
| 35 | POST | `/escrow/{escrow_id}/refund-request` | Escrow | Yes | BUYER owner | NOT TESTED |
| 36 | POST | `/escrow/{escrow_id}/release` | Escrow | Yes | FARMER seller or ADMIN | NOT TESTED |
| 37 | GET | `/farmers/me` | Farmers | Yes | FARMER | NOT TESTED |
| 38 | PUT | `/farmers/me` | Farmers | Yes | FARMER | NOT TESTED |
| 39 | GET | `/farms` | Farms | Yes | FARMER | NOT TESTED |
| 40 | POST | `/farms` | Farms | Yes | FARMER | NOT TESTED |
| 41 | DELETE | `/farms/{farm_id}` | Farms | Yes | FARMER owner | NOT TESTED |
| 42 | GET | `/farms/{farm_id}` | Farms | Yes | FARMER owner | NOT TESTED |
| 43 | PATCH | `/farms/{farm_id}` | Farms | Yes | FARMER owner | NOT TESTED |
| 44 | GET | `/health` | Health | No | Public | NOT TESTED |
| 45 | GET | `/health/ready` | Health | No | Public | NOT TESTED |
| 46 | GET | `/market-prices` | Market Prices | Yes | Any authenticated user | NOT TESTED |
| 47 | POST | `/market-prices` | Market Prices | Yes | AGRICULTURAL_OFFICER or ADMIN | NOT TESTED |
| 48 | GET | `/market-prices/compare` | Market Prices | Yes | Any authenticated user | NOT TESTED |
| 49 | GET | `/market-prices/history` | Market Prices | Yes | Any authenticated user | NOT TESTED |
| 50 | POST | `/market-prices/{price_id}/revision` | Market Prices | Yes | AGRICULTURAL_OFFICER or ADMIN | NOT TESTED |
| 51 | GET | `/marketplace/products` | Marketplace | No | Public | NOT TESTED |
| 52 | POST | `/marketplace/products` | Marketplace | Yes | FARMER | NOT TESTED |
| 53 | GET | `/marketplace/products/mine` | Marketplace | Yes | FARMER owner | NOT TESTED |
| 54 | DELETE | `/marketplace/products/{product_id}` | Marketplace | Yes | FARMER owner | NOT TESTED |
| 55 | GET | `/marketplace/products/{product_id}` | Marketplace | No | Public | NOT TESTED |
| 56 | PATCH | `/marketplace/products/{product_id}` | Marketplace | Yes | FARMER owner | NOT TESTED |
| 57 | GET | `/notifications/mine` | Notifications | Yes | Any authenticated user; own history | NOT TESTED |
| 58 | POST | `/notifications/send` | Notifications | Yes | AGRICULTURAL_OFFICER or ADMIN | NOT TESTED |
| 59 | POST | `/orders` | Orders | Yes | BUYER | NOT TESTED |
| 60 | GET | `/orders/buyer` | Orders | Yes | BUYER owner | NOT TESTED |
| 61 | GET | `/orders/seller` | Orders | Yes | FARMER | NOT TESTED |
| 62 | GET | `/orders/{order_id}` | Orders | Yes | Buyer, seller, or ADMIN (participant) | NOT TESTED |
| 63 | POST | `/orders/{order_id}/cancel` | Orders | Yes | BUYER owner | NOT TESTED |
| 64 | PATCH | `/orders/{order_id}/status` | Orders | Yes | FARMER seller | NOT TESTED |
| 65 | GET | `/payments/admin/history` | Payments | Yes | ADMIN | NOT TESTED |
| 66 | POST | `/payments/callback/daraja` | Payments | No | Public provider callback | NOT TESTED |
| 67 | POST | `/payments/initiate` | Payments | Yes | BUYER owner | NOT TESTED |
| 68 | GET | `/payments/mine` | Payments | Yes | BUYER | NOT TESTED |
| 69 | POST | `/payments/mock/{payment_id}/callback` | Payments | Yes | BUYER owner | NOT TESTED |
| 70 | GET | `/payments/{payment_id}` | Payments | Yes | Payment buyer or ADMIN | NOT TESTED |
| 71 | GET | `/payments/{payment_id}/provider-status` | Payments | Yes | Payment buyer or ADMIN | NOT TESTED |
| 72 | GET | `/payouts/{escrow_id}` | Payouts | Yes | Order buyer, seller, or ADMIN | NOT TESTED |
| 73 | POST | `/payouts/{escrow_id}/release` | Payouts | Yes | FARMER seller or ADMIN | NOT TESTED |
| 74 | GET | `/transactions/orders/{order_id}/ledger` | Transactions | Yes | Order buyer, seller, or ADMIN | NOT TESTED |
| 75 | GET | `/weather/forecast` | Weather | Yes | FARMER, AGRICULTURAL_OFFICER, or ADMIN | NOT TESTED |

**Count check:** 75 method/path entries across 59 paths, matching `app.openapi()` during generation. Recheck after code changes at `/openapi.json`.

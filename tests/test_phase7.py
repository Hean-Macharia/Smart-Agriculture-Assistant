from copy import deepcopy
from datetime import date, datetime, timezone
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.dependencies import get_advisory_repository, get_current_user, get_crop_repository, get_farm_repository, get_market_price_repository, get_notification_repository, get_user_repository, sms_provider
from app.main import app
from app.models.user import UserRole
from app.schemas.user import UserPublic
from app.schemas.weather import WeatherForecastPoint, WeatherObservation, WeatherResponse
from app.services.sms_providers import HttpSmsProvider, MockSmsProvider, SmsProviderError
from app.services.notification_service import dispatch_sms_event

FARMER = "64b000000000000000000001"
BUYER = "64b000000000000000000003"
OFFICER = "64b000000000000000000006"
ADMIN = "64b000000000000000000005"
FARM = "64b000000000000000000010"
CROP = "64b000000000000000000011"


def public_user(user_id, role):
    now = datetime.now(timezone.utc)
    return UserPublic(id=user_id, full_name="Test User", email="user@example.test", phone="0712345678", role=role, is_active=True, created_at=now, updated_at=now)


class MemoryMarketPrices:
    def __init__(self): self.items = {}
    def create(self, values):
        doc = {**deepcopy(values), "id":str(ObjectId()), "created_at":datetime.now(timezone.utc)}
        self.items[doc["id"]] = doc
        return deepcopy(doc)
    def get(self, price_id): return deepcopy(self.items.get(price_id))
    def create_revision(self, price_id, recorded_by, changes):
        prior = self.get(price_id)
        if prior is None: return None
        values = {k:prior[k] for k in ("crop_name","market_location","county","unit","data_source","source_name")}
        values.update(changes, recorded_by=recorded_by, supersedes_id=price_id)
        return self.create(values)
    def list_prices(self, *, crop_name, county, market_location, start_date, end_date, skip, limit):
        docs = list(self.items.values())
        if crop_name: docs = [d for d in docs if d["crop_name"].casefold()==crop_name.casefold()]
        if county: docs = [d for d in docs if d["county"].casefold()==county.casefold()]
        if market_location: docs = [d for d in docs if d["market_location"].casefold()==market_location.casefold()]
        if start_date: docs = [d for d in docs if d["date_collected"]>=start_date]
        if end_date: docs = [d for d in docs if d["date_collected"]<=end_date]
        docs.sort(key=lambda d:(d["date_collected"],d["created_at"]),reverse=True)
        return deepcopy(docs[skip:skip+limit]),len(docs)
    def compare(self, *, crop_name, county):
        docs,_=self.list_prices(crop_name=crop_name,county=county,market_location=None,start_date=None,end_date=None,skip=0,limit=1000)
        latest={}
        for d in docs: latest.setdefault((d["county"],d["market_location"],d["unit"]),d)
        return list(latest.values())


class MemoryAdvisories:
    def __init__(self): self.items={}
    def create(self, values):
        doc={**deepcopy(values),"id":str(ObjectId()),"created_at":datetime.now(timezone.utc),"updated_at":datetime.now(timezone.utc)}
        self.items[doc["id"]]=doc
        return deepcopy(doc)
    def get(self, aid): return deepcopy(self.items.get(aid))
    def list_for_farmer(self, *, farmer_id,crop_name,county,skip,limit):
        docs=[d for d in self.items.values() if d.get("farmer_id")==farmer_id or d["kind"]=="OFFICER" and d["is_active"] and (not d.get("crop_name") or not crop_name or d["crop_name"].casefold()==crop_name.casefold()) and (not d.get("county") or not county or d["county"].casefold()==county.casefold())]
        return deepcopy(docs[skip:skip+limit]),len(docs)
    def list_all(self, *, skip,limit,active_only=True):
        docs=[d for d in self.items.values() if d["kind"]=="OFFICER" and (not active_only or d["is_active"])]
        return deepcopy(docs[skip:skip+limit]),len(docs)
    def list_for_farmer_history(self,fid,*,skip,limit):
        docs=[d for d in self.items.values() if d.get("farmer_id")==fid]
        return deepcopy(docs[skip:skip+limit]),len(docs)
    def update_officer(self,aid,author_id,changes,*,is_admin):
        d=self.items.get(aid)
        if not d or d["kind"]!="OFFICER" or not is_admin and d["author_id"]!=author_id: return None
        d.update(deepcopy(changes),updated_at=datetime.now(timezone.utc)); return deepcopy(d)


class MemoryFarms:
    def get(self,fid): return {"id":FARM,"owner_id":FARMER,"county":"Nakuru"} if fid==FARM else None


class MemoryCrops:
    def get(self,cid): return {"id":CROP,"owner_id":FARMER,"farm_id":FARM,"name":"Maize"} if cid==CROP else None


class MemoryUsers:
    def get_by_id(self,uid):
        if uid not in {FARMER,BUYER,OFFICER,ADMIN}: return None
        return {"_id":ObjectId(uid),"phone":"0712345678","is_active":True}


class MemoryNotifications:
    def __init__(self): self.items={}
    def create_pending(self,values):
        prior=next((x for x in self.items.values() if x["idempotency_key"]==values["idempotency_key"]),None)
        if prior:
            if any(prior[k]!=values[k] for k in ("recipient_user_id","event","message","recipient_phone")): raise ValueError("Idempotency key conflict")
            return deepcopy(prior),False
        d={**deepcopy(values),"id":str(ObjectId()),"status":"PENDING","created_at":datetime.now(timezone.utc)}
        self.items[d["id"]]=d;return deepcopy(d),True
    def claim(self,nid):
        d=self.items[nid]
        if d["status"]!="PENDING":return None
        d["status"]="SENDING";return deepcopy(d)
    def finish(self,nid,*,status,provider_reference):
        d=self.items[nid];d.update(status=status,provider_reference=provider_reference);return deepcopy(d)
    def get(self,nid): return deepcopy(self.items.get(nid))
    def list_for_user(self,uid,*,skip,limit):
        d=[x for x in self.items.values() if x["recipient_user_id"]==uid];return deepcopy(d[skip:skip+limit]),len(d)


class CountingSmsProvider:
    name="http"
    def __init__(self,fail=False): self.calls=0;self.fail=fail
    def send_sms(self,*,to,message,idempotency_key):
        self.calls+=1
        if self.fail: raise SmsProviderError("provider down")
        return type("Result",(),{"simulated":False,"provider_reference":"gateway-accepted-123"})()


@pytest.fixture
def phase7_client(monkeypatch):
    current={"user":public_user(FARMER,UserRole.FARMER)}
    market,advisories,notifications=MemoryMarketPrices(),MemoryAdvisories(),MemoryNotifications()
    app.dependency_overrides[get_current_user]=lambda:current["user"]
    app.dependency_overrides[get_market_price_repository]=lambda:market
    app.dependency_overrides[get_advisory_repository]=lambda:advisories
    app.dependency_overrides[get_farm_repository]=MemoryFarms
    app.dependency_overrides[get_crop_repository]=MemoryCrops
    app.dependency_overrides[get_user_repository]=MemoryUsers
    app.dependency_overrides[get_notification_repository]=lambda:notifications
    monkeypatch.setattr(settings,"sms_provider","mock")
    monkeypatch.setattr(settings,"app_env","test")
    with TestClient(app) as client:
        yield client,current,market,advisories,notifications
    app.dependency_overrides.clear()


def test_market_price_add_filter_compare_and_revision_preserve_history(phase7_client):
    client,current,prices,_,_=phase7_client
    current["user"]=public_user(OFFICER,UserRole.AGRICULTURAL_OFFICER)
    body={"crop_name":"Maize","market_location":"Nakuru Market","county":"Nakuru","price_kes":5000,"unit":"90kg bag","date_collected":"2026-11-01","data_source":"MANUAL","source_name":"County market survey"}
    first=client.post("/market-prices",json=body)
    assert first.status_code==201
    first_id=first.json()["id"]
    current["user"]=public_user(FARMER,UserRole.FARMER)
    assert client.get("/market-prices?crop_name=maize&county=Nakuru").json()["total"]==1
    assert client.get("/market-prices/compare?crop_name=Maize").json()["items"][0]["price_kes"]==5000
    assert client.get("/market-prices/history?crop_name=Maize").json()["total"]==1
    current["user"]=public_user(OFFICER,UserRole.AGRICULTURAL_OFFICER)
    revised=client.post(f"/market-prices/{first_id}/revision",json={"price_kes":5200,"date_collected":"2026-11-02","source_name":"Second county market survey"})
    assert revised.status_code==201 and revised.json()["supersedes_id"]==first_id
    assert len(prices.items)==2
    assert prices.get(first_id)["price_kes"]==5000


def test_market_price_write_requires_officer_or_admin(phase7_client):
    client,_,_,_,_=phase7_client
    response=client.post("/market-prices",json={})
    assert response.status_code==403


def test_officer_advisory_is_visible_by_crop_and_admin_can_manage(phase7_client):
    client,current,_,advisories,_=phase7_client
    current["user"]=public_user(OFFICER,UserRole.AGRICULTURAL_OFFICER)
    created=client.post("/advisories",json={"title":"County planting update","message":"Contact your local extension officer for current seasonal planting dates.","crop_name":"Maize","county":"Nakuru","source_name":"Nakuru County Agriculture Office"})
    assert created.status_code==201
    aid=created.json()["id"]
    current["user"]=public_user(FARMER,UserRole.FARMER)
    assert client.get("/advisories?crop_name=Maize&county=Nakuru").json()["total"]==1
    assert client.get("/advisories?crop_name=Beans&county=Nakuru").json()["total"]==0
    current["user"]=public_user(ADMIN,UserRole.ADMIN)
    assert client.patch(f"/advisories/{aid}",json={"is_active":False}).status_code==200
    assert advisories.get(aid)["is_active"] is False


def test_weather_rule_recommendation_saves_farm_crop_and_forecast_context(phase7_client,monkeypatch):
    import app.routes.advisory as route
    client,current,_,advisories,_=phase7_client
    current["user"]=public_user(FARMER,UserRole.FARMER)
    now=datetime.now(timezone.utc)
    forecast=WeatherResponse(latitude=-0.3,longitude=36.1,source="Test Weather",retrieved_at=now,current=WeatherObservation(observed_at=now,temperature_c=22,rainfall_mm=0,humidity_percent=60,conditions="clouds"),forecast=[WeatherForecastPoint(forecast_at=now,temperature_c=22,rainfall_mm=0,humidity_percent=60,conditions="clouds") for _ in range(8)])
    monkeypatch.setattr(route,"fetch_weather_forecast",lambda lat,lon:forecast)
    response=client.post("/advisories/recommendations/weather",json={"farm_id":FARM,"crop_id":CROP,"latitude":-0.3,"longitude":36.1})
    assert response.status_code==201
    data=response.json()
    assert data["kind"]=="WEATHER_RULE" and data["farm_id"]==FARM and data["crop_name"]=="Maize"
    assert data["rules_applied"]==["LOW_RAINFALL_24H"]
    assert client.get("/advisories/mine").json()["total"]==1
    assert "not a diagnosis" in data["message"]


def test_weather_route_returns_unavailable_without_key_and_maps_provider_payload(monkeypatch):
    import app.services.weather_service as service
    from app.services.weather_service import WeatherProviderError, fetch_weather_forecast
    monkeypatch.setattr(settings,"weather_api_key","")
    with pytest.raises(WeatherProviderError): fetch_weather_forecast(-1.0,36.0)
    monkeypatch.setattr(settings,"weather_api_key","safe-test-key")
    class Response:
        def __init__(self,payload):self.payload=payload
        def raise_for_status(self):pass
        def json(self):return self.payload
    class Client:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,url,params):
            if url.endswith("/weather"):return Response({"dt":1794000000,"main":{"temp":21.5,"humidity":70},"rain":{"1h":1.2},"weather":[{"description":"light rain"}]})
            return Response({"list":[{"dt":1794003600,"main":{"temp":22,"humidity":68},"rain":{"3h":2.1},"weather":[{"description":"rain"}]}]})
    monkeypatch.setattr(service.httpx,"Client",Client)
    result=fetch_weather_forecast(-1.0,36.0)
    assert result.current.rainfall_mm==1.2 and result.forecast[0].rainfall_mm==2.1


def test_weather_endpoint_requires_allowed_role_and_configured_key(phase7_client,monkeypatch):
    client,current,_,_,_=phase7_client
    monkeypatch.setattr(settings,"weather_api_key","")
    assert client.get("/weather/forecast?latitude=-1&longitude=36").status_code==503
    current["user"]=public_user(BUYER,UserRole.BUYER)
    assert client.get("/weather/forecast?latitude=-1&longitude=36").status_code==403


def test_sms_mock_is_explicit_and_idempotent(phase7_client):
    client,current,_,_,notifications=phase7_client
    current["user"]=public_user(ADMIN,UserRole.ADMIN)
    app.dependency_overrides[sms_provider]=MockSmsProvider
    body={"recipient_user_id":BUYER,"event":"NEW_ORDER","message":"A new order is waiting for you."}
    headers={"Idempotency-Key":"test-notification-001"}
    first=client.post("/notifications/send",headers=headers,json=body)
    second=client.post("/notifications/send",headers=headers,json=body)
    assert first.status_code==second.status_code==200
    assert first.json()["notification"]["status"]=="SIMULATED"
    assert "no message was sent" in first.json()["detail"]
    assert len(notifications.items)==1


def test_sms_http_adapter_reports_accepted_and_provider_failure(phase7_client,monkeypatch):
    client,current,_,_,notifications=phase7_client
    current["user"]=public_user(OFFICER,UserRole.AGRICULTURAL_OFFICER)
    provider=CountingSmsProvider()
    app.dependency_overrides[sms_provider]=lambda:provider
    monkeypatch.setattr(settings,"sms_provider","http")
    body={"recipient_user_id":BUYER,"event":"DELIVERY_UPDATE","message":"Your produce is now in transit."}
    first=client.post("/notifications/send",headers={"Idempotency-Key":"sms-accepted-0001"},json=body)
    assert first.status_code==200 and first.json()["notification"]["status"]=="ACCEPTED"
    assert "not confirmed" in first.json()["detail"]
    provider.fail=True
    failed=client.post("/notifications/send",headers={"Idempotency-Key":"sms-failure-0001"},json=body)
    assert failed.status_code==502 and failed.json()["notification"]["status"]=="FAILED"
    assert len(notifications.items)==2


def test_automatic_sms_event_dispatch_is_opt_in_and_idempotent(phase7_client,monkeypatch):
    _,_,_,_,notifications=phase7_client
    import app.core.dependencies as dependencies
    provider=CountingSmsProvider()
    app.dependency_overrides[sms_provider]=lambda:provider
    monkeypatch.setattr(dependencies,"get_user_repository",MemoryUsers)
    monkeypatch.setattr(dependencies,"get_notification_repository",lambda:notifications)
    monkeypatch.setattr(dependencies,"sms_provider",lambda:provider)
    monkeypatch.setattr(settings,"sms_provider","http")
    monkeypatch.setattr(settings,"sms_auto_dispatch",True)
    dispatch_sms_event(recipient_user_id=BUYER,event="REGISTRATION",event_id="registered-user-1",message="Your account was created.")
    dispatch_sms_event(recipient_user_id=BUYER,event="REGISTRATION",event_id="registered-user-1",message="Your account was created.")
    assert provider.calls==1
    assert next(iter(notifications.items.values()))["status"]=="ACCEPTED"


def test_generic_http_sms_adapter_uses_https_and_reports_provider_acceptance(monkeypatch):
    import app.services.sms_providers as sms
    monkeypatch.setattr(settings,"sms_api_url","https://sms.example.test/v1/send")
    monkeypatch.setattr(settings,"sms_api_key","unit-test-secret")
    monkeypatch.setattr(settings,"sms_sender_id","AGRI")
    calls=[]
    class Response:
        def raise_for_status(self):pass
        def json(self):return {"message_id":"gateway-001"}
    def fake_post(url,**kwargs):
        calls.append((url,kwargs));return Response()
    monkeypatch.setattr(sms.httpx,"post",fake_post)
    result=HttpSmsProvider().send_sms(to="0712345678",message="Test notification",idempotency_key="sms-adapter-test-001")
    assert result.simulated is False and result.provider_reference=="gateway-001"
    assert calls[0][1]["headers"]["Idempotency-Key"]=="sms-adapter-test-001"
    assert calls[0][1]["json"]["sender_id"]=="AGRI"
    assert "unit-test-secret" not in repr(result)
    monkeypatch.setattr(settings,"sms_api_url","http://sms.example.test/send")
    with pytest.raises(SmsProviderError):
        HttpSmsProvider().send_sms(to="0712345678",message="Test",idempotency_key="sms-adapter-test-002")

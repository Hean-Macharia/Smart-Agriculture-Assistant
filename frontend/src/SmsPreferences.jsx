import {useEffect,useState} from "react";
import {api} from "./api.js";

const categories=[
 ["WEATHER_ALERT","Weather alerts"],["PLANTING_REMINDER","Planting reminders"],
 ["CROP_MANAGEMENT_REMINDER","Crop reminders"],["AGRICULTURAL_ADVISORY","Agricultural advice"],
 ["MARKET_PRICE","Market prices"],["BUYER_ENQUIRY","Buyer enquiries"],
 ["NEW_ORDER","Order updates"],["PAYMENT_CONFIRMATION","Payment status"],
 ["DELIVERY_UPDATE","Delivery updates"],["DISEASE_WARNING","Crop health warnings"],
];

export default function SmsPreferences(){
 const [preferences,setPreferences]=useState(null);
 const [selected,setSelected]=useState([]);
 const [language,setLanguage]=useState("en");
 const [busy,setBusy]=useState(false);
 const [notice,setNotice]=useState("");
 const [error,setError]=useState("");
 useEffect(()=>{let active=true;api("/notifications/preferences").then(data=>{if(!active)return;setPreferences(data);setSelected(data.categories||[]);setLanguage(data.language||"en")}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[]);
 const save=async consented=>{setBusy(true);setError("");setNotice("");try{const data=await api("/notifications/preferences",{method:"PUT",body:JSON.stringify({consented,language,categories:consented?selected:[]})});setPreferences(data);setSelected(data.categories||[]);setNotice(consented?"SMS preferences saved. You can reply STOP by SMS at any time.":"SMS messages are switched off.")}catch(e){setError(e.message)}finally{setBusy(false)}};
 if(!preferences&&!error)return <section className="panel sms-settings" aria-busy="true"><p role="status">Loading SMS preferences…</p></section>;
 return <section className="panel sms-settings"><small className="eyebrow">PHONE ACCESS</small><h2>SMS information</h2><p>Choose whether ShambaLink may send useful farm updates to <b>{preferences?.phone_number||"your account phone"}</b>. You can opt out at any time.</p>
  {error&&<p className="panel-error" role="alert">{error}</p>}{notice&&<p className="sms-notice" role="status">{notice}</p>}
  <label className="sms-language">Message language<select value={language} onChange={e=>setLanguage(e.target.value)}><option value="en">English</option><option value="sw">Kiswahili</option></select></label>
  <fieldset className="sms-categories"><legend>Choose message types</legend>{categories.map(([value,label])=><label key={value}><input type="checkbox" checked={selected.includes(value)} onChange={e=>setSelected(current=>e.target.checked?[...current,value]:current.filter(item=>item!==value))}/>{label}</label>)}</fieldset>
  <p className="sms-delivery-note">Phone verification: <b>{preferences?.phone_verified?"verified":"not verified"}</b>. After saving consent, text <b>START</b> from this phone to the service number given by your provider before SMS can be sent. Reply <b>STOP</b> to opt out. Provider acceptance does not confirm handset delivery.</p>
  <div className="sms-actions"><button className="btn btn-primary" type="button" disabled={busy} onClick={()=>save(true)}>{busy?"Saving…":"Give consent and save"}</button><button className="btn btn-outline" type="button" disabled={busy} onClick={()=>save(false)}>Turn SMS off</button></div>
 </section>;
}

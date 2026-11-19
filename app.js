const API = "http://127.0.0.1:8000";
let trendChart;
const $ = (id) => document.getElementById(id);
const num = (v, digits=0) => v === null || v === undefined ? "--" : Number(v).toFixed(digits);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function categoryClass(c){return (c||"unknown").replaceAll(" ","-").toLowerCase()}
function showToast(message){$("toast").textContent=message;$("toast").classList.add("show");setTimeout(()=>$("toast").classList.remove("show"),2500)}
async function api(path, options={}) {
  const response = await fetch(API + path, options);
  if(!response.ok){let detail="API request failed";try{detail=(await response.json()).detail||detail}catch{};throw new Error(detail)}
  return response.json();
}
function renderCities(cities){
  $("cityGrid").innerHTML = cities.map(c=>`
    <article class="city-card ${c.city==="Lahore"?"selected":""}">
      <div class="city-name">${esc(c.city)}</div>
      <div class="city-aqi">${num(c.aqi)}</div>
      <div class="city-label"><span class="dot-status ${categoryClass(c.category)}"></span>${esc(c.aqi_label)}</div>
      <div class="city-bottom"><span>PM2.5 ${num(c.pm2_5,1)}</span><span>${esc(c.time?.slice(11,16)||"--:--")}</span></div>
    </article>`).join("");
}
function renderLahore(city){
  const c=city.current, label=city.current.us_aqi;
  const [desc,cat]=aqiLabel(label);
  $("mainAqi").textContent=num(label);
  $("mainPm").textContent=num(c.pm2_5,1);
  $("aqiDescription").textContent=desc;
  $("lahoreStatus").textContent=desc;
  $("lahoreStatus").style.color=cat==="hazardous"||cat==="unhealthy"||cat==="very-unhealthy"?"#ff9292":"#ffbd78";
  $("pm10").textContent=num(c.pm10,1);$("temp").textContent=num(c.temperature,1);
  $("humidity").textContent=num(c.humidity);$("wind").textContent=num(c.wind_speed,1);
  $("updatedText").textContent=`Last refreshed ${new Date(city.updated_at).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"})} · Open-Meteo`;
  const percent=Math.max(4,Math.min(100,(Number(c.pm2_5)||0)/100*100));
  document.querySelector(".meter-ring").style.background=`conic-gradient(var(--teal) 0 ${percent}%,#1b3a4a ${percent}% 100%)`;
}
function aqiLabel(v){if(v==null)return ["Unavailable","unknown"];if(v<=50)return["Good","good"];if(v<=100)return["Moderate","moderate"];if(v<=150)return["Unhealthy for sensitive groups","sensitive"];if(v<=200)return["Unhealthy","unhealthy"];if(v<=300)return["Very unhealthy","very-unhealthy"];return["Hazardous","hazardous"]}
function renderPrediction(p){
  if(!p.available){$("predictionContent").innerHTML=`<div class="prediction-meta">${esc(p.reason)}</div>`;return}
  const sign=p.change>0?"+":"";
  $("predictionContent").innerHTML=`<div class="prediction-value">${num(p.next_hour_pm2_5,1)}<span style="font-size:13px;color:#86a2ad"> µg/m³</span></div><div class="prediction-meta">Predicted next-hour PM2.5<br><span class="prediction-change">${sign}${num(p.change,1)} µg/m³</span> vs current · Validation MAE ${num(p.validation_mae,2)}</div>`;
}
function renderChart(rows){
  const valid=rows.filter(r=>r.pm2_5!=null).slice(-24);
  const ctx=$("trendChart").getContext("2d");
  if(trendChart)trendChart.destroy();
  trendChart=new Chart(ctx,{type:"line",data:{labels:valid.map(r=>r.time.slice(11,16)),datasets:[{data:valid.map(r=>r.pm2_5),borderColor:"#54e0c0",backgroundColor:"rgba(84,224,192,.10)",fill:true,tension:.35,pointRadius:0,borderWidth:2}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{displayColors:false}},scales:{x:{ticks:{color:"#718d99",maxTicksLimit:6,font:{size:8}},grid:{display:false},border:{display:false}},y:{ticks:{color:"#718d99",font:{size:8}},grid:{color:"rgba(145,180,190,.08)"},border:{display:false}}}}});
}
function renderAdvice(items){
  $("adviceList").innerHTML=items.map((a,i)=>`<div class="advice-item ${esc(a.level)}"><span class="advice-symbol">${a.level==="high"?"!":a.level==="medium"?"↗":"✓"}</span><div><strong>${esc(a.title)}</strong><p>${esc(a.detail)}</p></div></div>`).join("");
}
async function loadDashboard(){
  $("refreshBtn").textContent="↻ Loading";
  try{
    const d=await api("/api/dashboard");
    renderCities(d.cities);renderLahore(d.lahore);renderPrediction(d.prediction);
    renderChart(d.lahore.hourly);renderAdvice(d.advice);
    $("todayLabel").textContent="LIVE MONITORING";
    showToast("Live air-quality data refreshed");
  }catch(e){showToast("Could not load live data: "+e.message);$("updatedText").textContent="Live data unavailable — check backend / internet."}
  finally{$("refreshBtn").textContent="↻ Refresh"}
}
async function sendMessage(message){
  if(!message.trim())return;
  const area=$("chatMessages");
  area.insertAdjacentHTML("beforeend",`<div class="chat-bubble user">${esc(message)}</div>`);
  $("chatInput").value="";
  area.scrollTop=area.scrollHeight;
  try{
    const result=await api("/api/assistant",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message})});
    area.insertAdjacentHTML("beforeend",`<div class="chat-bubble bot">${esc(result.answer)}</div>`);
  }catch(e){area.insertAdjacentHTML("beforeend",`<div class="chat-bubble bot">Assistant is unavailable: ${esc(e.message)}</div>`)}
  area.scrollTop=area.scrollHeight;
}
$("refreshBtn").addEventListener("click",loadDashboard);
$("chatForm").addEventListener("submit",e=>{e.preventDefault();sendMessage($("chatInput").value)});
document.querySelectorAll(".suggestion").forEach(b=>b.addEventListener("click",()=>sendMessage(b.textContent)));
loadDashboard();
setInterval(loadDashboard,10*60*1000);

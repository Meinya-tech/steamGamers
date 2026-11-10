const VERSION='telegram-queue-v1';
const FIELDS={nickname:40,game:80,steam:200,level:40,goal:50,schedule:80,timezone:80,about:500};
const json=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
export function validate(data){
 if(!data||typeof data!=='object'||data.consent!==true||data.adult!==true||data.broadcastConsent!==true||data.consentVersion!==VERSION)throw new Error('Подтвердите возраст и оба согласия.');
 const clean={};for(const [key,max] of Object.entries(FIELDS)){const v=data[key]??'';if(typeof v!=='string'||v.length>max||v.includes('\0')||(key!=='about'&&!v.trim()))throw new Error('Проверьте поля анкеты.');clean[key]=v.trim();}
 if(clean.nickname.length<2||!/^https:\/\/steamcommunity\.com\/(?:id\/[A-Za-z0-9_-]+|profiles\/\d{17})\/?$/.test(clean.steam))throw new Error('Проверьте никнейм и публичную ссылку Steam.');
 return clean;
}
async function digest(value){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value)))].map(x=>x.toString(16).padStart(2,'0')).join('');}
async function authorized(request,env){const expected=env.SG_QUEUE_SECRET;if(!expected||expected.length<32)return false;return await digest(request.headers.get('Authorization')||'')===await digest('Bearer '+expected);}
async function body(request){const length=Number(request.headers.get('Content-Length')||0);if(length>8192)throw new Error('Слишком большой запрос.');const reader=request.body?.getReader();if(!reader)throw new Error('Пустой запрос.');let size=0;const chunks=[];while(true){const r=await reader.read();if(r.done)break;size+=r.value.length;if(size>8192){await reader.cancel();throw new Error('Слишком большой запрос.');}chunks.push(r.value);}const result=new Uint8Array(size);let offset=0;for(const chunk of chunks){result.set(chunk,offset);offset+=chunk.length;}return JSON.parse(new TextDecoder().decode(result));}
export async function api(request,env){
 const url=new URL(request.url),path=url.pathname;
 if(path.startsWith('/api/queue/')){
  if(!await authorized(request,env))return json({error:'Unauthorized'},401);
  if(path==='/api/queue/pending'&&request.method==='GET'){
   // Expired records are removed before export; cloud copies live at most 7 days.
   await env.DB.prepare('DELETE FROM queue WHERE created < ?').bind(Date.now()-7*86400000).run();
   const rows=await env.DB.prepare("SELECT id,payload,created,consent_version FROM queue WHERE state='pending' ORDER BY created LIMIT 25").all();
   return json({applications:rows.results.map(r=>({id:r.id,data:JSON.parse(r.payload),created:new Date(r.created).toISOString(),consentVersion:r.consent_version}))});
  }
  if(path==='/api/queue/ack'&&request.method==='POST'){
   let data;try{data=await body(request);}catch{return json({error:'Invalid request'},400);}
   if(!Array.isArray(data.ids)||data.ids.length>25||data.ids.some(id=>typeof id!=='string'||!/^[a-f0-9]{24}$/.test(id)))return json({error:'Invalid ids'},400);
   if(data.ids.length)await env.DB.batch(data.ids.map(id=>env.DB.prepare("UPDATE queue SET state='received',payload='{}' WHERE id=?").bind(id)));
   return json({ok:true});
  }
  return json({error:'Not found'},404);
 }
 if(path!=='/api/applications'||request.method!=='POST')return json({error:'Not found'},404);
 if(request.headers.get('Origin')!==url.origin)return json({error:'Недопустимый источник запроса.'},403);
 if(!request.headers.get('Content-Type')?.startsWith('application/json'))return json({error:'Ожидается JSON.'},415);
 const key=request.headers.get('Idempotency-Key')||'';if(!/^[A-Za-z0-9-]{16,80}$/.test(key))return json({error:'Обновите страницу и повторите отправку.'},400);
 let data;try{data=validate(await body(request));}catch(error){return json({error:error instanceof SyntaxError?'Проверьте анкету.':error.message},400);}
 const old=await env.DB.prepare('SELECT id FROM queue WHERE request_key=?').bind(key).first();if(old)return json({id:old.id,message:'Заявка уже сохранена.'},201);
 if(!env.SG_QUEUE_SECRET)return json({error:'Приём заявок временно недоступен.'},503);
 const now=Date.now(),profile=await digest(data.steam),ip=await digest(env.SG_QUEUE_SECRET+':'+(request.headers.get('CF-Connecting-IP')||'unknown'));
 // A single atomic INSERT enforces limits even for concurrent requests.
 const id=crypto.randomUUID().replaceAll('-','').slice(0,24);
 const result=await env.DB.prepare(`INSERT OR IGNORE INTO queue(id,request_key,payload,profile_hash,ip_hash,created,consent_version)
 SELECT ?,?,?,?,?,?,? WHERE (SELECT COUNT(*) FROM queue WHERE created>?)<30
 AND NOT EXISTS(SELECT 1 FROM queue WHERE profile_hash=? AND created>?)
 AND (SELECT COUNT(*) FROM queue WHERE ip_hash=? AND created>?)<5`)
 .bind(id,key,JSON.stringify(data),profile,ip,now,VERSION,now-60000,profile,now-60000,ip,now-60000).run();
 if(!result.meta.changes){const raced=await env.DB.prepare('SELECT id FROM queue WHERE request_key=?').bind(key).first();if(raced)return json({id:raced.id},201);return json({error:'Слишком частые заявки. Подождите минуту.'},429);}
 return json({id,message:'Заявка сохранена. Бот заберёт её, когда компьютер организатора будет доступен.'},201);
}
export default {async fetch(request,env){
 const path=new URL(request.url).pathname;
 if(path.startsWith('/api/')){try{return await api(request,env);}catch{return json({error:'Сервис временно недоступен. Повторите отправку позже с теми же данными.'},503);}}
 const file=ASSETS[path==='/'?'/index.html':path];
 if(!file)return new Response('Not found',{status:404});
 if(!['GET','HEAD'].includes(request.method))return new Response('Method not allowed',{status:405});
 const bytes=Uint8Array.from(atob(file.body),c=>c.charCodeAt(0));
 return new Response(request.method==='HEAD'?null:bytes,{headers:{'Content-Type':file.type,'Cache-Control':'no-cache','X-Content-Type-Options':'nosniff','Referrer-Policy':'strict-origin-when-cross-origin'}});
}};

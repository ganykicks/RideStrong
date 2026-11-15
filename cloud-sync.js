import { createClient } from 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.57.4/+esm';
const URL='https://byvdrawehcgdbflwblds.supabase.co';
const KEY='sb_publishable_-HMmDaQoS-JyVFBZ4pA9Ng_-IlRi9LL';
export function installRideStrongCloud(api) {
  const db=createClient(URL,KEY,{auth:{persistSession:true,autoRefreshToken:true,detectSessionInUrl:true}});
  const section=document.getElementById('export').closest('section');
  const heading=section.querySelector('h2');
  heading.textContent='Workout records · Cloud sync and JSON backup';
  const para=heading.nextElementSibling;
  para.textContent='Sign in to synchronize your completed and skipped workouts across devices. Records are also saved locally for offline use. JSON backup is still available.';
  const view=document.createElement('div');
  view.className='card';
  view.style.margin='10px 0';
  view.innerHTML='<h3>Automatic cloud synchronization</h3><p id="syncAccount">Checking sign-in…</p>'+
    '<div id="syncLoggedOut"><label>Email for secure sign-in <input type="email" id="syncEmail" autocomplete="email" placeholder="you@example.com"></label>'+
    '<button id="syncLogin" type="button">Email me a sign-in link</button></div>'+
    '<div id="syncLoggedIn" style="display:none"><div class="row"><button id="syncNow" type="button">Sync now</button>'+
    '<button id="syncLegacy" class="alt" type="button" style="display:none">Import old records from this browser</button>'+
    '<button id="syncLogout" class="alt" type="button">Sign out</button></div></div>'+
    '<p id="syncStatus" class="status" aria-live="polite">Cloud sync not connected.</p>'+
    '<p class="muted" style="font-size:13px">Use the same email on all devices. Offline edits synchronize when you reconnect. If you already used RideStrong before signing in, import those records once with the button above.</p>';
  heading.insertAdjacentElement('afterend',view);
  const $=id=>document.getElementById(id);
  let active=null,version=0, running=false,queued=false;
  const accountKey=id=>'ridestrong_v3_cloud_'+id;
  const when=r=>Date.parse(r?.updatedAt||'')||0;
  const status=s=>$('syncStatus').textContent=s;
  const localRecords=()=>{
    try {let x=JSON.parse(localStorage.getItem('ridestrong_v3')||'{}');return x&&typeof x==='object'&&!Array.isArray(x)?x:{};}catch{return {};}
  };
  const legacyCount=()=>Object.entries(localRecords()).filter(([k,v])=>api.validKey(k)&&api.validRecord(v)).length;
  const showLegacy=()=>{let n=legacyCount();$('syncLegacy').style.display=active&&n?'inline-block':'none';$('syncLegacy').textContent='Import '+n+' earlier record(s) from this browser';};
  async function identity(user) {
    const prior=active?.id;
    if (user?.id===prior) return;
    version++;active=user||null;
    if (!user){
      window.rideStrongScopedKey=null;
      window.rideStrongOnPersist=null;
      api.setRecords(localRecords());
      $('syncAccount').textContent='Not signed in. Your workouts still save on this device.';
      $('syncLoggedOut').style.display='block';
      $('syncLoggedIn').style.display='none';
      status('Cloud sync is off. Your local workout history is preserved.');
      return;
    }
    const uid=user.id;
    window.rideStrongScopedKey=accountKey(uid);
    let existing={};
    try {existing=JSON.parse(localStorage.getItem(accountKey(uid))||'{}');if(!existing||Array.isArray(existing)||typeof existing!=='object')existing={};}catch{}
    api.setRecords(existing);
    window.rideStrongOnPersist=()=>{queued=true;void synchronize();};
    $('syncAccount').textContent='Signed in as '+(user.email||'your account');
    $('syncLoggedOut').style.display='none';
    $('syncLoggedIn').style.display='block';
    showLegacy();
    status('Connected. Checking cloud progress…');
    queued=true;void synchronize();
  }
  async function synchronize(){
    if(!active || running || !navigator.onLine)return;
    running=true;const v=version,uid=active.id;
    try{
      do{
        queued=false;
        const {data:rows,error:readError}=await db.from('ride_progress').select('workout_date,status,reason,client_updated_at').order('workout_date',{ascending:true});
        if(readError)throw readError;
        if(v!==version||uid!==active?.id)return;
        let current={...api.getRecords()},remote={};
        for(const row of rows||[]){
          let rec={status:row.status,reason:row.reason||'',updatedAt:row.client_updated_at};
          if(!api.validKey(row.workout_date)||!api.validRecord(rec))continue;
          remote[row.workout_date]=rec;
          if(when(rec)>when(current[row.workout_date]))current[row.workout_date]=rec;
        }
        api.setRecords(current);
        localStorage.setItem(accountKey(uid),JSON.stringify(current));
        const pending=Object.entries(current).filter(([k,rec])=>api.validKey(k)&&api.validRecord(rec)&&when(rec)>when(remote[k]));
        for(const [day,rec] of pending){
          if(v!==version||uid!==active?.id)return;
          const {error}=await db.rpc('ride_progress_merge',{p_date:day,p_status:rec.status,p_reason:rec.reason||'',p_updated_at:rec.updatedAt});
          if(error)throw error;
        }
        status('Cloud synchronized · '+new Date().toLocaleTimeString()+'. '+pending.length+' change(s) uploaded.');
      }while(queued && v===version);
    }catch(err){
      if(v===version)status('Cloud sync failed: '+(err?.message||String(err))+'. Local progress is safe; retry with Sync now.');
    }finally {running=false;if(queued&&v===version&&navigator.onLine)void synchronize();}
  }
  $('syncLogin').onclick=async()=>{
    const email=$('syncEmail').value.trim();
    if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)){status('Enter a valid email address.');return;}
    $('syncLogin').disabled=true;
    try{
      const {error}=await db.auth.signInWithOtp({email,options:{emailRedirectTo:location.origin+location.pathname}});
      if(error)throw error;
      status('Check your email for the RideStrong sign-in link. Open it on this device.');
    }catch(e){status('Sign-in request failed: '+e.message);}
    finally{$('syncLogin').disabled=false;}
  };
  $('syncNow').onclick=()=>{queued=true;void synchronize();};
  $('syncLogout').onclick=async()=>{const {error}=await db.auth.signOut();if(error)status('Sign-out failed: '+error.message);else await identity(null);};
  $('syncLegacy').onclick=()=>{
    if(!active)return;
    const old=localRecords(),current={...api.getRecords()};let added=0;
    for(const [k,rec] of Object.entries(old)){
      if(!api.validKey(k)||!api.validRecord(rec))continue;
      if(when(rec)>when(current[k])){current[k]=rec;added++;}
    }
    api.setRecords(current);api.persist();
    showLegacy();status(added+' earlier records added to this account. Syncing…');
  };
  window.addEventListener('online',()=>{queued=true;void synchronize();});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden){queued=true;void synchronize();}});
  db.auth.onAuthStateChange((_event,session)=>{setTimeout(()=>{void identity(session?.user||null);},0);});
  void db.auth.getUser().then(({data,error})=>{if(error){status('Sign-in check failed: '+error.message);return;}void identity(data.user);})
    .catch(e=>status('Cloud initialization error: '+e.message));
}

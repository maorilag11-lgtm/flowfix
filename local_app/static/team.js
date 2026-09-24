"use strict";
(()=>{
let token='';const $=id=>document.getElementById(id);const el=(tag,text)=>{const e=document.createElement(tag);if(text)e.textContent=text;return e;};
async function api(path,body){const r=await fetch(path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-FlowFix-Token':token},body:body===undefined?undefined:JSON.stringify(body)});const d=await r.json();if(r.status===401){location.href='/login/?next=/team/';throw Error('Reconnectez-vous.');}if(!r.ok)throw Error(d.error||'Erreur de communication.');return d;}
async function run(fn){const buttons=[...document.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);$('team-status').textContent='';try{await fn();}catch(e){$('team-status').textContent=e.message;}finally{buttons.forEach(b=>b.disabled=false);}}
async function load(){const d=await api('/api/team');$('team-seats').textContent='Votre équipe : '+(d.members.length+1)+' membre(s), '+d.invitations.length+' invitation(s) en attente · '+d.seats+' siège(s) disponibles dans l’offre.';
for(const id of ['team-spaces','team-members','team-invitations'])$(id).replaceChildren();
const action=(parent,label,operation,id)=>{const b=el('button',label);b.onclick=()=>{if(!confirm('Confirmer : '+label+' ?'))return;run(async()=>{const r=await api('/api/team',{operation,id});await load();$('team-status').textContent=r.message;});};parent.append(b);};
for(const s of d.spaces){const row=el('article');const a=el('a',s.name+' · '+s.team);a.href='/app/?workspace='+encodeURIComponent(s.id)+'#new';row.append(a,el('p','Rôle : '+({owner:'Propriétaire',editor:'Éditeur',viewer:'Lecture seule'}[s.role])));if(s.role==='owner')action(row,'Supprimer cet espace','delete_space',s.id);$('team-spaces').append(row);}
if(!d.spaces.length)$('team-spaces').append(el('p',d.seats>1?'Créez votre premier espace client avec le formulaire ci-dessus.':'Aucun espace partagé. Activez votre essai dans les paramètres pour en créer un.'));
for(const m of d.members){const row=el('article',m.email+' · '+(m.role==='editor'?'Éditeur':'Lecture seule'));action(row,'Révoquer l’accès','revoke',m.id);$('team-members').append(row);}
for(const i of d.invitations){const row=el('article',i.email+' · Invitation en attente jusqu’au '+new Date(i.expires).toLocaleDateString('fr-FR'));action(row,'Annuler l’invitation','cancel_invite',i.id);$('team-invitations').append(row);}}
for(const [id,operation] of [['team-accept','accept'],['team-space','create_space'],['team-invite','invite']])$(id).onsubmit=e=>{e.preventDefault();const form=e.currentTarget;run(async()=>{const d=await api('/api/team',{...Object.fromEntries(new FormData(form)),operation});if(d.code){$('team-code').value=d.code;$('team-code-label').hidden=false;}await load();$('team-status').textContent=d.message;form.reset();});};
run(async()=>{token=(await api('/api/config')).csrf;await load();});
})();

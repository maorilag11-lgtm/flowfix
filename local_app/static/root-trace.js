'use strict';
let traceModules=[], preservedTrace=null;
const traceEl=id=>document.getElementById(id);
function tracePath(parts){return '/'+parts.map(x=>String(x).replace(/~/g,'~0').replace(/\//g,'~1')).join('/');}
function setTraceModules(modules){traceModules=modules;refreshTraceMappings();}
function refreshTraceMappings(){
 const select=traceEl('trace-mapping'),previous=select.value;
 select.replaceChildren(new Option('Sélectionnez une référence de mapping',''));
 const mid=traceEl('module-select').value;
 for(const m of traceModules.find(m=>m.id===mid)?.trace_mappings||[]){select.append(new Option('Module '+m.source_module_id+' '+tracePath(m.source_field_path)+' → '+tracePath(m.target_field_path),JSON.stringify(m)));}
 if([...select.options].some(o=>o.value===previous))select.value=previous;
 traceEl('trace-mapping-help').textContent=select.options.length>1?'Chemins issus du Blueprint, pas des libellés Make vérifiés.':'Aucun mapping direct reconnu pour ce module. Ajoutez le Blueprint et choisissez le module ; les expressions calculées ne sont pas prises en charge.';
}
function resetTraceForm(){preservedTrace=null;traceEl('trace-advanced-details').open=false;traceEl('trace-advanced-enabled').checked=false;traceEl('trace-details').open=false;traceEl('trace-preserved').hidden=true;traceEl('trace-replace').hidden=true;traceEl('trace-fields').hidden=false;traceEl('trace-enabled').checked=false;}
function restoreTraceContext(ctx){
 refreshTraceMappings();if(!ctx)return;
 // Retain all evidence, including API-created dossiers that this single-boundary editor cannot represent.
 traceEl('trace-advanced-json').value=JSON.stringify(ctx,null,2);
 preservedTrace=structuredClone(ctx);traceEl('trace-enabled').checked=true;traceEl('trace-preserved').hidden=false;traceEl('trace-preserved').textContent='Les preuves enregistrées sont conservées intégralement. Une modification archive les données et le résultat précédents dans l’historique. Pour une nouvelle reproduction, renseignez son exécution et son erreur sans réutiliser les preuves de l’ancienne panne.';traceEl('trace-replace').hidden=false;traceEl('trace-fields').hidden=true;
}
function strictTraceJSON(text){
 const value=JSON.parse(text);const tokens=text.match(/"(?:\\.|[^"\\])*"|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null|[{}\[\]:,]/g)||[];let pos=0;
 function walk(depth){if(depth>24)throw Error('Le JSON est trop imbriqué.');const token=tokens[pos++];if(token==='{'){const keys=new Set();while(tokens[pos]!=='}'){const key=JSON.parse(tokens[pos++]);if(keys.has(key))throw Error('Le JSON contient une clé dupliquée : '+key);keys.add(key);pos++;walk(depth+1);if(tokens[pos]!==',')break;pos++;}pos++;}else if(token==='['){while(tokens[pos]!==']'){walk(depth+1);if(tokens[pos]!==',')break;pos++;}pos++;}}
 walk(0);if(value===null||Array.isArray(value)||typeof value!=='object')throw Error('Collez un objet JSON à la racine de la sortie.');return value;
}
function readTraceContext(){
 if(!traceEl('trace-enabled').checked)return null;
 if(traceEl('trace-advanced-enabled').checked)return strictTraceJSON(traceEl('trace-advanced-json').value);
 if(preservedTrace)return structuredClone(preservedTrace);
 function need(id,label){const v=traceEl(id).value.trim();if(!v)throw Error('Traçage : '+label+' est nécessaire. Ouvrez « Examiner les données en amont ».');return v;}
 const selected=need('trace-mapping','un mapping explicite');const m=JSON.parse(selected);
 if(m.target_module_id!==traceEl('module-select').value)throw Error('Sélectionnez à nouveau le mapping du module en erreur.');
 const required=traceEl('trace-required').checked?true:null;
 const expectedType=traceEl('trace-type').value;
 const nullable=traceEl('trace-nullable').value===''?null:traceEl('trace-nullable').value==='true';
 const minItems=traceEl('trace-nonempty').checked?1:null;
 if(minItems!==null&&expectedType!=='array')throw Error('Pour exiger un tableau non vide, choisissez le type Tableau.');
 if(required===null&&expectedType==='UNKNOWN'&&nullable!==false&&minItems===null)throw Error('Précisez au moins une exigence à vérifier ou désactivez le traçage.');
 const payload=strictTraceJSON(need('trace-payload','la sortie JSON'));
 const sourceBundle=need('trace-source-bundle','le bundle source');
 const run=need('trace-run','l’identifiant d’exécution');
 const observedAt=traceEl('trace-observed-at').value.trim()||null;
 if(observedAt&&(!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(observedAt)||!Number.isFinite(Date.parse(observedAt))))throw Error('Indiquez une date ISO complète avec fuseau, par exemple 2026-09-24T14:30:00+02:00.');
 const correlations=[];
 if(traceEl('trace-correlated').checked){
  const targetRun=need('trace-target-run','l’exécution du bundle cible');
  if(targetRun!==run)throw Error('Les bundles source et cible appartiennent à des exécutions différentes. Conservez-les dans des dossiers séparés.');
  const method=need('trace-correlation-method','la méthode de rapprochement');
  const c={correlation_id:'ui-correlation',observation_id:'ui-output',target_module_id:m.target_module_id,target_bundle_id:need('trace-target-bundle','le bundle cible'),target_execution_id:targetRun,method,provenance:{source_ref:need('trace-correlation-source','la source de correspondance des bundles')}};
  if(method==='CORRELATION_KEY')c.correlation_key=need('trace-correlation-key','la clé de corrélation');
  correlations.push(c);
 }
 return {execution_id:run,scenario_version:traceEl('trace-version').value.trim()||null,
 observations:[{observation_id:'ui-output',execution_id:run,evidence_origin:traceEl('trace-origin').value,observed_at:observedAt,module_id:m.source_module_id,direction:'OUTPUT',bundle_id:sourceBundle,data_path:[],observed_value:payload,completeness:traceEl('trace-completeness').value,redaction_state:traceEl('trace-redaction').value,provenance:{source_ref:need('trace-observation-source','la source de la sortie')}}],
 expectations:[{expectation_id:'ui-expectation',target_module_id:m.target_module_id,target_field_path:m.target_field_path,required,expected_type:expectedType,nullable,min_items:minItems,provenance:{source_ref:need('trace-expectation-source','la source des exigences sélectionnées')}}],correlations};
}
function renderRootTrace(trace){
 const host=traceEl('trace-result');host.replaceChildren();host.hidden=!trace;if(!trace)return;
 const labels={NOT_ESTABLISHED:'Origine amont non établie',CANDIDATES:'Pistes en amont à vérifier',INVALID_BOUNDARY_OBSERVED:'Écart constaté sur une dépendance',CONTRADICTED:'Des preuves se contredisent'};
 host.append(node('p','TRAÇAGE DES DONNÉES','eyebrow'),node('h2',labels[trace.status]||'Traçage non disponible'));
 if(trace.execution_id)host.append(node('p','Exécution examinée : '+trace.execution_id+(trace.scenario_version?' · Version : '+trace.scenario_version:'')));
 if(trace.symptom_location?.module_id)host.append(node('p','Symptôme signalé au module '+trace.symptom_location.module_id+'.'));
 host.append(node('p',trace.status==='CONTRADICTED'?'Résolvez les contradictions avant de retenir une conclusion ou modifier le scénario.':'Cette lecture repose sur les preuves fournies. Elle ne confirme pas l’origine première de la panne.'));
 const confidenceLabels={unknown:'indéterminée',low:'faible',medium:'modérée',high:'élevée'};
 host.append(node('p','Confiance du constat local : '+(confidenceLabels[trace.confidence]||'indéterminée')+'.'));
 for(const b of trace.invalid_boundary_observed||[]){
  const section=node('section',undefined,'trace-boundary');section.append(node('strong','Module '+b.source_module_id+' → module '+b.target_module_id),node('p','Dépendance de données, pas nécessairement une connexion directe d’exécution.'),node('p','Champ source : '+tracePath(b.source_field_path||b.missing_source_path)+'. Champ cible : '+tracePath(b.target_field_path)+'.'));
  const typeLabels={string:'texte',number:'nombre',boolean:'booléen',object:'objet',array:'tableau',null:'null',UNKNOWN:'non précisé'};
  const mismatchLabels={REQUIRED_FIELD_ABSENT:'Le champ est absent alors que sa présence est explicitement exigée.',TYPE_MISMATCH:'Type observé : '+(typeLabels[b.observed_type]||'inconnu')+'. Type attendu : '+(typeLabels[b.expected_type]||'inconnu')+'.',NULL_NOT_ALLOWED:'La valeur observée est null ; l’attente fournie interdit explicitement null.',EMPTY_ARRAY_NOT_ALLOWED:'Le tableau observé contient 0 élément ; l’attente fournie en exige au moins 1.'};
  for(const code of b.mismatch_codes||['REQUIRED_FIELD_ABSENT'])section.append(node('p',mismatchLabels[code]||'Écart à vérifier.'));
  section.append(node('p','Comparez la sortie enregistrée de la source avec l’entrée du module cible. Vérifiez l’exigence avant de corriger le mapping ou la source ; aucune valeur de remplacement n’est déduite.'));
  if(trace.status==='CONTRADICTED')section.append(node('p','Constat local conservé, mais aucune conclusion globale en raison des contradictions.'));
  host.append(section);
 }
 if(trace.status==='CANDIDATES')host.append(node('p',(trace.upstream_candidates||[]).length+' piste(s) conservée(s), sans cause unique désignée.'));
 const reasons={MISMATCH_NOT_ESTABLISHED:'Aucun écart n’est démontré avec cette observation et les exigences fournies. Cela ne valide pas le scénario.',EXPLICIT_SYMPTOM_REQUIRED:'Sélectionnez explicitement le module en erreur.',INVALID_CONTEXT:'Vérifiez le format des preuves fournies.',UNRESOLVED_DEPENDENCY:'Une référence de module reste inconnue ou ambiguë.',EXACT_EXPECTATION_REQUIRED:'Précisez l’exigence du champ cible et sa source.',OUTPUT_OBSERVATION_REQUIRED:'Ajoutez la sortie du module source.',BUNDLE_CORRELATION_REQUIRED:'Vérifiez quels bundles source et cible se correspondent.',REQUIRED_ABSENCE_NOT_ESTABLISHED:'Les données ne démontrent pas l’absence du champ requis.',NO_SUPPORTED_EXPLICIT_MAPPING:'Aucun mapping direct pris en charge ne permet cette comparaison.',DEPENDENCY_LIMIT:'Trop de dépendances pour conclure dans ce périmètre.',COMPARISON_LIMIT:'La limite de comparaison a été atteinte.',BOUNDARY_LIMIT:'La limite de frontières a été atteinte.'};
 const states={EMPTY_ARRAY:'présent avec un tableau vide',ABSENT:'absent dans l’observation complète',NULL:'présent avec la valeur null',EMPTY_STRING:'présent avec une chaîne vide',REDACTED:'masqué ou masquage inconnu',PARTIAL_OBSERVATION:'observation partielle',NOT_PROVIDED:'observation non fournie à ce chemin',PRESENT:'présent'};
 if(trace.missing_information?.length){host.append(node('h3','Pour affiner'));const ul=node('ul');for(const text of new Set(trace.missing_information.map(m=>(reasons[m.code]||'Une preuve complémentaire est nécessaire.')+(m.state?' État : '+(states[m.state]||'inconnu')+'.':''))))ul.append(node('li',text));host.append(ul);}
 const warnings={OBSERVATION_DATE_UNKNOWN:'Date d’observation inconnue.',OBSERVATION_ORIGIN_UNKNOWN:'Origine historique ou reproduction non précisée.',OBSERVATION_RUN_INHERITED:'Exécution reprise du dossier, non précisée sur l’observation.',LEGACY_BUNDLE_DECLARATION:'Ancienne déclaration de correspondance : méthode et exécution cible non détaillées.'};
 if(trace.evidence_warnings?.length){const note=node('details');note.append(node('summary','Limites des preuves d’exécution'));for(const w of trace.evidence_warnings)note.append(node('p',w.subject_ref+' · '+(warnings[w.code]||'Preuve à préciser.')));host.append(note);}
 const paths=trace.observed_data_paths||[];
 if(paths.some(p=>p.module_ids.length>2)){host.append(node('h3','Chemins de données observés'));for(const path of paths){host.append(node('p',path.module_ids.join(' → ')));host.append(node('p','Liens déclarés pour les bundles fournis. '+(path.stop_reason==='OBSERVED_SCOPE_START'?'Le périmètre observé commence ici ; l’origine antérieure reste inconnue.':'La remontée s’arrête : une preuve intermédiaire manque ou une limite a été atteinte.')));}}
 if(paths.some(p=>p.module_ids.length>2))for(const first of trace.earliest_invalid_boundary_within_observed_scope||[]){const boundary=(trace.invalid_boundary_observed||[]).find(b=>b.boundary_id===first.boundary_ref);if(boundary)host.append(node('p','Premier écart observé sur ce chemin : module '+boundary.source_module_id+' → module '+boundary.target_module_id+'. Ce constat reste limité aux champs et aux preuves fournis.'));}
 if(trace.operator_findings?.length){host.append(node('h3','Contrôles locaux des opérateurs'));const names={FILTER:'Filtre',ITERATOR:'Iterator',AGGREGATOR:'Aggregator'};const statuses={INVALID_CONTRACT_OBSERVED:'Écart au contrat observé',NO_MISMATCH_OBSERVED:'Aucun écart observé sur les contrôles fournis',NOT_ESTABLISHED:'Preuves insuffisantes',CONTRADICTED:'Preuves contradictoires'};const codes={FILTER_OUTCOME_MISMATCH:'Le passage ou blocage observé diffère de l’attente déclarée.',EXPECTED_ARRAY_NOT_OBSERVED:'Le contrat exige un tableau ; la donnée observée ne correspond pas.',BUNDLE_COUNT_MISMATCH:'Le nombre observé diffère du nombre attendu dans ce périmètre.',REQUIRED_FIELD_ABSENT:'Un champ de sortie obligatoire est absent.',TYPE_MISMATCH:'Le type d’un champ de sortie ne correspond pas à l’attente.',NULL_NOT_ALLOWED:'Un champ de sortie vaut null alors que cela est interdit.',EMPTY_ARRAY_NOT_ALLOWED:'Un tableau de sortie est vide alors que cela est interdit.'};
 for(const check of trace.operator_findings){const box=node('section',undefined,'trace-boundary');box.append(node('strong',(names[check.kind]||'Opérateur')+' · Module '+check.module_id),node('p',statuses[check.status]||'À vérifier'));for(const code of check.mismatch_codes||[])box.append(node('p',codes[code]||'Écart à vérifier.'));if(check.observed_count!==undefined)box.append(node('p','Nombre observé : '+check.observed_count+' · Attendu : '+check.expected_count));if(check.observed_outcome)box.append(node('p','Résultat observé : '+({PASSED:'passage',BLOCKED:'blocage',UNKNOWN:'inconnu'}[check.observed_outcome])+' · Attendu : '+({PASSED:'passage',BLOCKED:'blocage',UNKNOWN:'inconnu'}[check.expected_outcome])));if(check.reason)box.append(node('p',check.reason==='UNSUPPORTED_OPERATOR_STRUCTURE'?'Ce type de module ou ce filtre n’est pas reconnu dans le Blueprint.':'Vérifiez les observations, leur cohérence et la complétude du périmètre.'));box.append(node('p','Contrôle limité aux preuves et au contrat déclarés. Il ne prouve pas l’origine de la panne.'));host.append(box);}}
 const details=node('details');details.append(node('summary','Voir les chemins et les preuves'));
 for(const path of trace.execution_paths||[])details.append(node('p','Chemin d’exécution explicite : '+path.join(' → ')));
 for(const f of trace.field_observations||[])details.append(node('p',f.observation_ref+' : '+(states[f.state]||f.state)));
 for(const e of trace.evidence_registry||[]){
  if(e.record_type==='observation')details.append(node('p',( {HISTORICAL:'Historique',REPRODUCTION:'Nouvelle reproduction',UNKNOWN:'Origine inconnue'}[e.evidence_origin]||'Origine inconnue')+' · Observation : '+(e.observed_at||'date inconnue')+' · Module '+e.module_id+' · Bundle '+e.bundle_id+' · '+e.direction));
  if(e.record_type==='correlation')details.append(node('p','Rapprochement déclaré : '+({HISTORY_LINK:'historique Make',CORRELATION_KEY:'clé commune',MANUAL:'vérification manuelle'}[e.method]||'ancienne déclaration')+' · Bundle cible '+e.target_bundle_id+' · Exécution cible '+(e.target_execution_id||'reprise du dossier')));
  const id=e.transition_id||e.check_id||e.correlation_id||e.expectation_id||e.observation_id||e.dependency_id;details.append(node('p',(e.provenance_kind==='STRUCTURAL'?'Structure fournie':'Déclaration fournie')+' · '+id+' · '+(e.provenance?.source_ref||e.blueprint_path||'Source non précisée')));}
 if(trace.contradictory_evidence?.length)details.append(node('p','Preuves contradictoires : '+trace.contradictory_evidence.join(', ')));
 details.append(node('p','L’origine avant le périmètre observé reste inconnue. Aucun changement n’est appliqué dans Make.'));host.append(details);
 const button=node('button','Compléter les preuves');button.type='button';button.id='trace-edit';button.onclick=()=>{traceEl('edit-session').click();};host.append(button);
}
traceEl('module-select').addEventListener('change',()=>{refreshTraceMappings();traceEl('trace-correlated').checked=false;});
traceEl('open-trace').onclick=()=>{traceEl('context-dialog').showModal();traceEl('trace-details').open=true;refreshTraceMappings();traceEl('trace-details').scrollIntoView({block:'start'});};
traceEl('trace-replace').onclick=()=>{preservedTrace=null;traceEl('trace-preserved').hidden=true;traceEl('trace-replace').hidden=true;traceEl('trace-fields').hidden=false;};

traceEl('trace-load-demo').onclick=()=>action(async()=>{
 const kind=traceEl('trace-demo-kind').value;const response=await fetch('/trace-examples.json');if(!response.ok)throw Error('Exemples indisponibles.');const examples=await response.json();const sample=examples[kind];
 resetDraft();workspace('new');blueprint=sample.blueprint;traceEl('error-text').value=sample.error;await populateModules();traceEl('module-select').value=sample.module;refreshTraceMappings();traceEl('filename').textContent='Blueprint de démonstration fictif';traceEl('optional-context').open=true;traceEl('trace-details').open=true;traceEl('trace-advanced-details').open=true;traceEl('trace-enabled').checked=true;traceEl('trace-advanced-enabled').checked=true;traceEl('trace-advanced-json').value=JSON.stringify(sample.root_cause_context,null,2);updateCount();
});

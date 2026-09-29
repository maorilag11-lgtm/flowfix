'use strict';
// Catalog is supplied by the server before this source-owned formatter.
window.flowfixText=function(value){
 if(typeof value!=='string'||window.flowfixLanguage!=='en')return value;
 if(Object.prototype.hasOwnProperty.call(window.flowfixCatalog,value))return window.flowfixCatalog[value];
 let m=value.match(/^Analyse offerte : (\d+) sur 3 restante\(s\). Aucun paiement effectué\.$/);
 if(m)return 'Free analysis: '+m[1]+' of 3 remaining. No payment taken.';
 m=value.match(/^Le message nomme « (.+) » et attend (.+)\. Comparez sa valeur et son type dans le bundle en échec avec cette exigence\. N’inventez pas de valeur de remplacement\.$/);
 if(m)return 'The message names “'+m[1]+'” and expects '+({'un entier':'an integer','un nombre':'a number','un booléen':'a boolean','un tableau':'an array','une adresse email':'an email address','du texte':'text'}[m[2]]||m[2])+'. Compare its value and type in the failed bundle with this requirement. Do not invent a replacement value.';
 m=value.match(/^Le message indique que « (.+) » est obligatoire\. Vérifiez si ce champ est vide ou absent dans le bundle en échec, puis remontez au mapping qui l’alimente\.$/);
 if(m)return 'The message says “'+m[1]+'” is required. Check whether this field is empty or absent in the failed bundle, then trace the mapping that supplies it.';
 m=value.match(/^Le message signale que le champ « (.+) » est vide ou obligatoire\. Ce constat vient du texte transmis, sans inspection du scénario Make\.$/);
 if(m)return 'The message reports that “'+m[1]+'” is empty or required. This finding comes from the supplied text, without inspecting the Make scenario.';
 m=value.match(/^Dans le module en erreur, inspectez le champ « (.+) » sur le bundle concerné\./);
 if(m)return 'In the failing module, inspect “'+m[1]+'” in the relevant bundle. Follow its mapping to the source data: check whether it exists, is empty or has another name. If missing, fix the source or define how incomplete items should be handled instead of inventing a value.';
 return value;
};
window.flowfixDisplay=function(data){
 const d={...data,output:{...data.output}};
 if(d.accounting)d.accounting={...d.accounting,message:flowfixText(d.accounting.message)};
 const f=d.output.first_reading;
 if(f)d.output.first_reading={...f,title:flowfixText(f.title),explanation:flowfixText(f.explanation),limitation:flowfixText(f.limitation),follow_up:flowfixText(f.follow_up),checks:(f.checks||[]).map(flowfixText),possibilities:(f.possibilities||[]).map(p=>({...p,title:flowfixText(p.title),explanation:flowfixText(p.explanation)})),references:(f.references||[]).map(r=>({...r,source_name:flowfixText(r.source_name)}))};
 const a=d.output.assessment;if(a)d.output.assessment={...a,title:flowfixText(a.title),detail:flowfixText(a.detail)};
 return d;
};

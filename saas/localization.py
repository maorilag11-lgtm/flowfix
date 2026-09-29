"""Source-owned UI translations. Never translate user input or stored evidence."""
import json,re
from functools import lru_cache
from pathlib import Path
from django.utils import translation
from django.template.loaders.filesystem import Loader as FilesystemLoader

@lru_cache(maxsize=1)
def catalog():
    pairs={}
    for line in (Path(__file__).parent/'locales/en.tsv').read_text().splitlines():
        if '\t' in line:
            source,target=line.split('\t',1);pairs[source]=target
    return pairs

def language():return 'fr' if translation.get_language()=='fr' else 'en'

def text(value):
    if not isinstance(value,str) or language()=='fr':return value
    if value in catalog():return catalog()[value]
    stripped=value.strip()
    if stripped in catalog():return value[:len(value)-len(value.lstrip())]+catalog()[stripped]+value[len(value.rstrip()):]
    # Server-generated accounting message, not user content.
    match=re.fullmatch(r'Analyse offerte : (\d+) sur 3 restante\(s\). Aucun paiement effectué.',value)
    if match:return f'Free analysis: {match[1]} of 3 remaining. No payment taken.'
    return value

def html_source(source):
    if language()=='fr':return source
    # Work on template/source text before user values are rendered. Preserve
    # template expressions, attributes carrying values, and all layout/animation hooks.
    parts=re.split(r'(\{%.*?%\}|\{\{.*?\}\}|<[^>]+>)',source,flags=re.S)
    for i,part in enumerate(parts):
        if part.startswith(('{%','{{')):continue
        if part.startswith('<'):
            part=re.sub(r'(\b(?:placeholder|aria-label|title|alt)=)(["\'])(.*?)(\2)',lambda m:m[1]+m[2]+text(m[3])+m[4],part)
            part=part.replace('lang="fr"','lang="en"')
            parts[i]=part
        else:parts[i]=text(part)
    return ''.join(parts)

def javascript_source(source):
    if language()=='fr':return source
    # Replace only complete, source-authored string literals, never substrings
    # of selectors, keys, imported Blueprints, or runtime user values.
    replacements={}
    for original,english in catalog().items():
        for quote in ["'",'"']:
            literal=quote+original.replace('\\','\\\\').replace(quote,'\\'+quote).replace('\n','\\n')+quote
            replacements[literal]=json.dumps(english,ensure_ascii=False)
    replacements["'fr-FR'"]="'en-US'"
    pattern=re.compile('|'.join(re.escape(key) for key in sorted(replacements,key=len,reverse=True)))
    return pattern.sub(lambda m:replacements[m[0]],source)

class Loader(FilesystemLoader):
    def get_contents(self,origin):return html_source(super().get_contents(origin))

class LanguageMiddleware:
    def __init__(self,get_response):self.get_response=get_response
    def __call__(self,request):
        lang=request.session.get('flowfix_language','en')
        if request.user.is_authenticated:
            from .models import Account
            lang=Account.objects.filter(user=request.user).values_list('language',flat=True).first() or 'en'
        if lang not in ('en','fr'):lang='en'
        request.LANGUAGE_CODE=lang
        with translation.override(lang):
            response=self.get_response(request)
            if response.get('Content-Type','').startswith('application/json') and not response.streaming:
                payload=json.loads(response.content)
                if isinstance(payload,dict):
                    for key in ('error','message','plan'):
                        if key in payload:payload[key]=text(payload[key])
                    for offer in payload.get('offers',[]):
                        if 'name' in offer:offer['name']=text(offer['name'])
                    response.content=json.dumps(payload,ensure_ascii=False,default=str).encode()
                    if response.has_header('Content-Length'):response['Content-Length']=str(len(response.content))
            response['Content-Language']=lang
            return response

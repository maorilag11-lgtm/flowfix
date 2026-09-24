"""Non-conclusive triage from redacted error text; never authorizes a correction.

Editorial checks reference the Make error taxonomy. KB references are included
only for literal codes/messages, never broad retrieval keyword overlap.
"""
import re
from flowfix.step1_intake.redaction.redactor import redact_dict
from flowfix.step5_response.formatter.guidance import _documents

SOURCE = 'https://help.make.com/fix-errors-and-warnings'
# code, label, explanation, conditional cause, read-only first check
RULES = (
    (r'\b401\b|\bAccountValidationError\b|\bUnauthorized\b', 'Authentification à vérifier',
     'Le message signale un refus lié à l’authentification.',
     'La connexion peut avoir expiré, avoir été révoquée ou utiliser des identifiants non acceptés.',
     'Dans Make, repérez la connexion du module en erreur et consultez son état. Comparez le compte connecté avec celui attendu par le service.'),
    (r'\b403\b|\bForbidden\b', 'Accès refusé',
     'Le service refuse l’accès à l’opération ou à la ressource demandée.',
     'Les droits du compte, les autorisations de la connexion ou l’accès à cette ressource peuvent être insuffisants.',
     'Vérifiez que le compte utilisé par le module a accès à la ressource et à cette opération dans le service cible.'),
    (r'\b429\b|\bRateLimitError\b|too many requests', 'Limite de requêtes atteinte',
     'Le message indique une limitation du rythme des appels.',
     'Plusieurs exécutions ou bundles peuvent envoyer trop de requêtes sur la même période.',
     'Consultez les limites du service et les horaires des appels en échec. Recherchez un délai Retry-After dans la réponse avant de planifier une nouvelle tentative.'),
    (r'\b422\b|unprocessable entity', 'Données refusées par le service',
     'Le code 422 indique que le service ne peut pas traiter les données envoyées.',
     'Un champ requis, un format ou une règle métier peut ne pas être respecté. Le code seul ne permet pas de choisir entre ces causes.',
     'Ouvrez la réponse complète de l’exécution en échec. Repérez le champ cité, puis comparez sa valeur reçue avec le format et les contraintes attendus par le service.'),
    (r'\bBundleValidationError\b|missing value of required parameter|required parameter.*missing', 'Entrée du module à vérifier',
     'Le module signale une valeur d’entrée absente ou non conforme.',
     'Un mapping peut fournir une valeur vide ou un type incompatible sur le bundle concerné.',
     'Repérez le paramètre nommé dans l’erreur. Dans le bundle en échec, vérifiez sa valeur et son type, puis remontez au module qui le fournit.'),
    (r'\bModuleTimeoutError\b|\bETIMEDOUT\b|timed? out|\btimeout\b', 'Délai de réponse dépassé',
     'L’opération n’a pas reçu de réponse dans le délai attendu.',
     'Le service peut être lent ou la demande trop coûteuse ; cela ne prouve pas une erreur de mapping.',
     'Consultez l’état du service cible et la durée de l’exécution. Avant une relance, vérifiez si l’opération a déjà été effectuée côté service pour éviter un doublon.'),
    (r'\bConnectionError\b|\bECONNREFUSED\b|\bENOTFOUND\b', 'Connexion au service impossible',
     'Le message signale un problème pour joindre le service.',
     'Une indisponibilité, une adresse incorrecte ou un problème réseau peut expliquer cet échec.',
     'Vérifiez l’adresse appelée et l’état du service cible, puis comparez avec une exécution récente qui a réussi.'),
    (r'\b(?:500|502|503|504)\b', 'Erreur côté service distant',
     'Le code signale une erreur de serveur ou de passerelle.',
     'Une indisponibilité temporaire du service est possible ; le message seul ne permet pas d’exclure une requête qui déclenche son erreur.',
     'Consultez la réponse complète et l’état du service. Vérifiez si les mêmes données fonctionnaient auparavant avant de changer le scénario.'),
    (r'\b404\b|not found', 'Ressource introuvable',
     'Le service ne trouve pas la ressource demandée.',
     'L’adresse ou l’identifiant peut être incorrect, ou la ressource peut avoir été supprimée ou être inaccessible à ce compte.',
     'Comparez l’URL et l’identifiant réellement envoyés avec une ressource visible pour le compte connecté.'),
    (r'\b400\b|bad request', 'Requête à vérifier',
     'Le service rejette la requête envoyée.',
     'Un paramètre, le corps de la requête ou son format peut ne pas correspondre à ce que l’API attend.',
     'Lisez le détail de la réponse puis comparez les paramètres et le corps envoyés avec un exemple accepté par la documentation de cette API.'),
    (r'\bJSON\b.*(?:invalid|syntax|parse)|(?:invalid|parse).*\bJSON\b', 'Syntaxe JSON à vérifier',
     'Le message indique que du texte n’a pas pu être interprété comme du JSON.',
     'Une ponctuation incorrecte, un texte non JSON ou une valeur injectée par mapping peut produire ce résultat.',
     'Inspectez le texte réellement reçu au moment de l’erreur et l’emplacement indiqué par le parseur. Ne corrigez pas seulement le modèle avant mapping.'),
)


def first_reading(problem, retrieval):
    error = '\n'.join(problem.errors.exact_error_messages)
    # Do not interpret an arbitrary module ID or product number as HTTP status.
    signal_text=re.sub(r'(?<!\w)([45]\d{2})(?!\w)', lambda m: m.group(0) if re.search(r'(?:http(?: status)?|status(?: code)?|code|error|erreur)\s*[:=]?\s*$|\[\s*$', error[:m.start()], re.I) or m.start()==0 or re.match(r'\s+(?:Unauthorized|Forbidden|Unprocessable|Too Many|Bad Request|Not Found|Internal Server|Service Unavailable|Bad Gateway|Gateway Timeout)',error[m.end():],re.I) else '',error)
    matches = [rule for rule in RULES if re.search(rule[0], signal_text, re.I)]
    result = dict(kind='preliminary', conclusive=False, execution_verified=False,
                  title='Première lecture de votre erreur',
                  limitation='Ces pistes reposent sur les informations transmises. Elles ne confirment ni la cause exacte ni une valeur à modifier.',
                  checks=[], possibilities=[], references=[])
    if matches:
        rule = matches[0]
        result.update(title=rule[1], explanation=rule[2])
        for _, label, _, cause, check in matches[:3]:
            result['possibilities'].append(dict(title=label, explanation=cause))
            result['checks'].append(check)
        result['references'].append(dict(source_name='Make — erreurs et avertissements', source_url=SOURCE))
    else:
        result['explanation']='Le message ne suffit pas à identifier une famille d’erreur avec fiabilité. Vous pouvez néanmoins localiser le point de rupture sans fournir de Blueprint.'
        result['checks']=[
            'Dans l’historique Make, ouvrez l’exécution en échec et le premier module qui signale une erreur.',
            'Comparez son bundle d’entrée avec celui d’une exécution réussie : cherchez une valeur absente, un type différent ou une ressource inaccessible.',
        ]
    # Extract an explicitly named parameter without inventing its value/type.
    field=re.search(r"missing value of required parameter\s+['\"]?([a-zA-Z_][\w.]{0,63})",error,re.I)
    typed=re.search(r"\b([a-zA-Z_][\w.]{0,63})\s+must be (?:a |an )?(?:valid )?(integer|number|boolean|array|email|string)\b",error,re.I)
    empty_field=re.search(r'"field"\s*:\s*"([a-zA-Z_][\w.]{0,63})"\s*,\s*"message"\s*:\s*"([^"\n]*(?:empty|null|required)[^"\n]*)"',error,re.I)
    if empty_field:
        result['explanation']=f"Le message signale que le champ « {empty_field[1]} » est vide ou obligatoire. Ce constat vient du texte transmis, sans inspection du scénario Make."
        result['checks'].insert(0,f"Dans le module en erreur, inspectez le champ « {empty_field[1]} » sur le bundle concerné. Suivez son mapping jusqu’à la donnée source : vérifiez si elle existe, est vide, ou porte un autre nom. Si elle manque, corrigez la source ou définissez le traitement métier des éléments incomplets plutôt qu’une valeur fictive.")
    if typed:
        names={'integer':'un entier','number':'un nombre','boolean':'un booléen','array':'un tableau','email':'une adresse email','string':'du texte'}
        result['checks'].insert(0,f"Le message nomme « {typed[1]} » et attend {names[typed[2].lower()]}. Comparez sa valeur et son type dans le bundle en échec avec cette exigence. N’inventez pas de valeur de remplacement.")
    elif field:
        result['checks'].insert(0,f"Le message indique que « {field[1]} » est obligatoire. Vérifiez si ce champ est vide ou absent dans le bundle en échec, puis remontez au mapping qui l’alimente.")
    # Only literal error identifiers or substantive phrases. HTTP codes must
    # appear in the title as well: shared "422" tags do not prove a date issue.
    for match in retrieval.matches:
        entry=match.entry
        if entry is None:continue
        codes=[str(c) for c in entry.error_codes if re.search(r'(?<!\w)'+re.escape(str(c))+r'(?!\w)',signal_text,re.I)]
        exact=any(not c.isdigit() or re.search(r'\b'+re.escape(c)+r'\b',entry.title) for c in codes)
        if not exact:continue
        docs=_documents(entry,[])
        for doc in docs:
            if doc.source_url and not any(x['source_url']==doc.source_url for x in result['references']):
                result['references'].append(dict(source_name=doc.source_name or entry.title,source_url=doc.source_url,entry_id=entry.id))
        if not matches and entry.diagnosis_steps:
            result['checks']=list(entry.diagnosis_steps[:3])
            result['explanation']='Une référence documentaire correspond au type d’erreur cité. Voici les contrôles qu’elle propose ; leur pertinence reste à vérifier sur votre exécution.'
            break
    result['references']=result['references'][:4]
    result['follow_up']='Pour affiner : ajoutez le détail complet de l’erreur, le nom du module et sa valeur d’entrée. Le Blueprint est facultatif et aide à examiner les liens entre modules.'
    return redact_dict(result).redacted_data

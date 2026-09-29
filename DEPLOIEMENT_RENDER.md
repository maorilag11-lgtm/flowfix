# FlowFix — préparer Render avec un dépôt privé

## État de cette livraison

Configuration préparée, pas de dépôt distant créé, pas de service déployé et pas de dépense engagée. L’archive source doit rester PRIVÉE : elle contient le moteur et la KB, même si ces fichiers ne sont pas servis par l’application.

`render.yaml` est écrit en JSON, syntaxe également valide en YAML. Il prévoit un service Docker payant Starter et un PostgreSQL payant 0.5 CPU / 1 Go, tous deux à Francfort, avec 5 Go de stockage. Ce choix est une base de préproduction, pas un dimensionnement validé par un test de charge. Vérifier le coût total affiché par Render avant toute création ; aucun tarif garanti par cette documentation.

Les déploiements automatiques sont désactivés. Le mode maintenance est activé pour empêcher l’ouverture du produit avant les contrôles. Cela n’arrête pas la facturation de ressources créées. La base bloque toutes les connexions externes avec `ipAllowList: []` ; l’application utilise les références internes de la base.

## Préparer les comptes

1. Créer ses comptes GitHub et Render et activer la double authentification. Garder les codes de récupération hors du dépôt.
2. Créer un dépôt GitHub **privé** dédié au produit. Y mettre le contenu décompressé de l’archive privée, avec `manage.py`, `Dockerfile` et `render.yaml` à la racine. Ne pas importer tout le dossier de travail, les bases SQLite ou les anciennes sauvegardes. Le fichier `.gitignore` ne protège pas les secrets déjà suivis par Git.
3. Autoriser Render à accéder uniquement à ce dépôt. Ne pas héberger l’archive comme un fichier téléchargeable sur Netlify ou dans les ressources statiques du produit.
4. Choisir le service d’email SMTP avant les tests de compte réels. Le code utilise STARTTLS, normalement sur le port 587 ; garder les clés dans les variables d’environnement Render.

## Configurer le Blueprint sans ouvrir le produit

Dans Render, préparer un Blueprint à partir du dépôt privé et vérifier les ressources et leur prix avant de confirmer leur création.

Variables à renseigner dans Render :

| Variable | Valeur attendue |
|---|---|
| `DJANGO_SECRET_KEY` | Secret aléatoire indépendant de plus de 50 caractères ; générer localement avec `python -c "import secrets; print(secrets.token_urlsafe(64))"`, puis saisir directement dans Render, jamais dans un commit ou une conversation |
| `DJANGO_ALLOWED_HOSTS` | Nom exact du service attribué par Render, puis le domaine personnalisé vérifié si utilisé ; liste séparée par des virgules, sans joker |
| `PUBLIC_URL` | Origine HTTPS exacte utilisée par les utilisateurs, sans chemin, incluse dans les hôtes autorisés |
| `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | Paramètres SMTP du fournisseur ; ne pas utiliser un backend console |
| `DEFAULT_FROM_EMAIL` | Expéditeur autorisé par le fournisseur SMTP |
| `SUPPORT_EMAIL` | Adresse de support opérationnelle |

La variable `DATABASE_URL` est reliée automatiquement à l’URL interne PostgreSQL. FlowFix la lit avec TLS requis ; ne pas remplacer cette URL par une connexion publique. Ne pas recopier la base SQLite de développement. Les paiements sont désactivés. Un domaine `flowfix.io` n’est ni réservé ni configuré par cette livraison ; commencer avec le nom réel attribué par Render si nécessaire.

Le pré-déploiement lance `check --deploy`, `release_check`, puis les migrations. Un contrôle qui échoue bloque cette étape. Ces commandes ne prouvent pas la délivrabilité email, la restauration, les règles réseau ou la résistance à la charge.

## Point à résoudre avant les testeurs : adresse IP derrière le proxy

Le proxy Caddy du déploiement Docker classique n’est pas utilisé dans cette configuration Render. **Ne pas activer `TRUST_CLIENT_IP=1` ici** : Render n’est pas configuré pour remplacer notre en-tête personnalisé `X-FlowFix-Client-IP`, qu’un client pourrait falsifier.

La configuration conserve donc `TRUST_CLIENT_IP=0`. Les limites par compte continuent à fonctionner, mais les limites par IP peuvent être partagées entre utilisateurs derrière le proxy Render. C’est un point de validation/adaptation restant avant l’ouverture de la bêta, pas une configuration finale de limitation par IP.

Render documente l’usage de `X-Forwarded-For`. Avant de l’utiliser pour des décisions de sécurité, établir la chaîne de proxys et vérifier le comportement avec des en-têtes forgés depuis plusieurs connexions. Ne pas prendre arbitrairement la première adresse d’un en-tête fourni par le client. Si le comportement ne peut pas être garanti, configurer un point d’entrée maîtrisé qui remplace l’en-tête ou adapter les limites pour ne pas dépendre d’une IP non fiable.

`TRUST_PROXY=1` sert uniquement au schéma HTTPS Django. Vérifier sur la plateforme la réécriture de `X-Forwarded-Proto`, l’absence de boucle de redirection et le refus des hôtes inattendus. Vérifier aussi que `/healthz` atteint effectivement le contrôle de base de données : une redirection seule ne constitue pas une preuve de bonne santé de la base.

## Contrôles avant ouverture

- Préproduction accessible seulement dans le cadre du test prévu ; le mode maintenance Render bloque aussi les parcours utilisateurs normaux. Prévoir un contrôle d’accès de préproduction avant de le lever pour ces tests.
- Image Docker construite et analysée sur un environnement disposant de Docker ; versions d’images de base figées après validation. Cette machine de préparation ne dispose pas de Docker.
- HTTPS, cookies, adresse IP fiable et limites de requêtes, isolation entre deux comptes, ancienne API `/api/knowledge` en 404.
- Emails réellement reçus, confirmation et récupération de mot de passe testées, domaines et journaux vérifiés sans conserver les liens secrets.
- Sauvegarde externalisée/chiffrée, restauration dans une autre base et alertes. Programmer `python manage.py clearsessions` quotidiennement et les réconciliations de facturation lorsque Stripe sera activé.
- Charge et concurrence sur PostgreSQL, quota de stockage global, droits et rétention. Les comptes inclus sans quota commercial ne doivent pas épuiser physiquement la base.

Une fois les contrôles concluants, décider explicitement l’ouverture et passer `maintenanceMode.enabled` à `false`. Ajouter le domaine personnalisé seulement lorsqu’il est possédé et vérifié. Configurer Stripe en sandbox avant tout passage au paiement réel.

## Sources vérifiées le 24 septembre 2026

- [Blueprint Render : champs, base et maintenance](https://render.com/docs/blueprint-spec)
- [Connexion à PostgreSQL](https://render.com/docs/postgresql-creating-connecting)
- [Contrôles de santé](https://render.com/docs/health-checks)
- [Proxys et protection réseau Render](https://render.com/articles/how-render-handles-ddos-attacks)

Ce guide prépare un déploiement ; il ne certifie pas une production opérationnelle ou invulnérable.

## Retour à la page de vente

Configurer `MARKETING_URL` avec l’URL HTTPS réelle du site commercial. Le logo FlowFix et « Retour à l’accueil » des écrans connexion, inscription et invitation bêta renvoient vers cette URL. En développement, la valeur par défaut est `http://127.0.0.1:8770/`. `PUBLIC_URL` reste l’URL du produit.

## Test gratuit — 29 septembre 2026

Le `render.yaml` racine décrit désormais uniquement le test gratuit : `flowfix-test`
et `flowfix-test-db` (Frankfurt, PostgreSQL 17). La configuration payante précédente
est conservée dans `deploy/render-paid.yaml` et n'est pas appliquée automatiquement.

Le démarrage `python deploy/start_test.py` conserve DEBUG désactivé, HTTPS, les
cookies sécurisés et PostgreSQL. Il déduit l'origine du nom fourni par Render,
valide la configuration puis applique les migrations avant de démarrer un seul
worker. Le secret est généré par Render. Aucun compte ni historique local n'est copié.

`release_check --test-deployment` dispense uniquement de la configuration SMTP,
avec un drapeau explicite et la facturation désactivée. Le contrôle commercial
sans cette option continue d'exiger les emails. Aucun paiement réel ne doit être
activé avec ce lanceur. Les emails de vérification et de récupération ne sont pas
opérationnels tant qu'un transport compatible avec Render Free n'est pas ajouté.

Limites : veille après 15 minutes, démarrage à froid, base gratuite expirant après
30 jours, absence de sauvegardes intégrées. Utiliser uniquement des données de test.
Le déploiement ne constitue pas une validation commerciale ni un audit de sécurité complet.

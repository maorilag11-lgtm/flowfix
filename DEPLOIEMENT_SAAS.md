# Déployer FlowFix pour une bêta SaaS

## Prérequis restant à fournir

Un hébergement Docker avec sauvegardes externes, un domaine dont le DNS pointe sur ce serveur, une adresse de support et un service SMTP. Pour activer les abonnements : compte Stripe, produit/prix récurrent et endpoint webhook. Ne pas placer les secrets dans le code, les archives ou la conversation.

Compléter aussi l’identité de l’exploitant, l’hébergeur, les durées de conservation et les conditions de la bêta dans la page `saas/templates/privacy.html`. Le texte livré est une description technique à compléter, pas une validation juridique. Fixer le prix, les quotas annoncés, le support inclus et les conditions de résiliation avant de vendre.

## Installation sur le serveur

1. Copier `.env.example` en `.env` et protéger le fichier (`chmod 600 .env`). Renseigner un secret Django aléatoire d’au moins 50 caractères, un mot de passe PostgreSQL distinct, `FLOWFIX_DOMAIN`, `DJANGO_ALLOWED_HOSTS` et `PUBLIC_URL=https://votre-domaine`.
2. Renseigner les variables SMTP et support. Garder `BILLING_ENABLED=0` pour commencer.
3. Construire puis migrer :

```sh
docker compose --env-file .env -f deploy/compose.yml build
docker compose --env-file .env -f deploy/compose.yml up -d db
docker compose --env-file .env -f deploy/compose.yml run --rm app python manage.py migrate --noinput
docker compose --env-file .env -f deploy/compose.yml run --rm app python manage.py check --deploy
docker compose --env-file .env -f deploy/compose.yml run --rm app python manage.py release_check
docker compose --env-file .env -f deploy/compose.yml up -d
```

Caddy termine HTTPS ; l’application et PostgreSQL ne publient aucun port externe. `TRUST_PROXY=1` est réservé à ce proxy qui réécrit `X-Forwarded-Proto`. Ne pas exposer Gunicorn directement. Restreindre les accès au serveur et au réseau de la base.

4. Vérifier HTTPS, les cookies Secure/HttpOnly, la connexion, deux comptes isolés, un export, une suppression et la réinitialisation reçue par email.
5. Créer une invitation via `docker compose --env-file .env -f deploy/compose.yml exec app python manage.py invite adresse@example.com`.

`release_check` contrôle la configuration ; il ne prouve pas la délivrabilité SMTP, l’isolation réseau, la restauration ou la validité des documents commerciaux.

## Sauvegarde et restauration

Programmer une sauvegarde PostgreSQL chiffrée vers un stockage externe. Définir et publier sa rétention. Exemple de création d’un dump (exécuter depuis un shell privé sur le serveur) :

```sh
docker compose --env-file .env -f deploy/compose.yml exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > flowfix-backup.dump
```

Ce dump contient les comptes et analyses : le chiffrer, limiter ses accès et ne pas l’inclure dans une archive de distribution. Tester `pg_restore` dans une base isolée, puis vérifier l’accès et les analyses de deux comptes de test avant d’ouvrir la bêta. Ne pas restaurer par-dessus la production pour faire ce test. En cas de restauration, réappliquer les demandes de suppression reçues depuis la sauvegarde.

## Exploitation

- Surveiller `/healthz` et les erreurs 5xx sans enregistrer les payloads ou cookies. Ce point contrôle la connexion à la base, pas l’ensemble du moteur.
- Alerter sur erreurs Stripe, indisponibilité SMTP, disque et base. Tester le temps de réponse et les quotas avec plusieurs comptes concurrents sur PostgreSQL.
- Programmer quotidiennement `python manage.py clearsessions`. Nettoyer les invitations utilisées/expirées et les compteurs de limitation devenus anciens selon la politique fixée.
- `python manage.py beta_metrics` produit des agrégats, sans Blueprints ni emails ; les statuts sont des déclarations utilisateurs, pas un taux de précision certifié.
- Appliquer les mises à jour de sécurité des dépendances et images, puis refaire les tests. Les images de base doivent être figées par digest après validation sur l’hôte cible.
- Les limites de connexion/inscription utilisent l’adresse réseau reçue. Dans le déploiement fourni, Caddy remplace explicitement `X-FlowFix-Client-IP` par son adresse cliente et `TRUST_CLIENT_IP=1` autorise sa lecture. Réserver ce réglage à ce réseau fermé ; le serveur applicatif ne doit pas être accessible en contournant le proxy. Les utilisateurs derrière une même adresse publique partagent une limite.

### Renforcement du 24 septembre 2026

Le démarrage en production refuse maintenant une clé Django manifestement faible, les hôtes génériques et un `PUBLIC_URL` qui ne correspond pas à une origine HTTPS explicitement autorisée. Cela ne mesure pas l’aléa réel de la clé : toujours la générer avec un générateur cryptographique. Le Compose fourni impose `FLOWFIX_DEV=0` même si le fichier `.env` contient une valeur de développement.

La connexion possède une limite supplémentaire de 30 tentatives par identifiant normalisé sur 15 minutes, indépendante de l’IP. La suppression du compte autorise au maximum 5 vérifications de mot de passe par compte sur 15 minutes ; Checkout et le portail partagent 30 demandes par compte sur cette période. Ce sont des limites applicatives, pas une protection DDoS. Un attaquant peut provoquer un blocage temporaire d’un identifiant connu : prévoir le support et une protection réseau adaptée.

Voir [le rapport de sécurité](product/security_20260924/AUDIT.md) pour les preuves de test, la portée et les contrôles de production encore à effectuer.

### Confirmation des adresses et récupération de compte

La migration `0006` ajoute la preuve de vérification d’adresse et un lien actif par compte. Les comptes existants ne sont pas automatiquement considérés comme vérifiés. Leurs accès déjà accordés et leurs analyses restent disponibles. Une adresse confirmée est nécessaire pour activer un nouvel essai, accepter une invitation d’équipe, démarrer une souscription et attribuer un achat LTD avec `fulfill_ltd`.

Le bouton « Confirmer mon adresse email » est dans Mon accès. L’utilisateur demande lui-même l’email depuis `/verify-email/`. Le lien expire après 24 heures, est remplacé par un nouvel envoi et doit être confirmé en POST depuis une session du compte concerné. Aucun email n’est envoyé automatiquement lors de l’inscription. Si SMTP n’est pas configuré ou échoue, le produit annonce l’indisponibilité sans prétendre avoir envoyé l’email. Les demandes d’envoi sont limitées à 3 par compte sur 15 minutes.

Renseigner `EMAIL_HOST`, `EMAIL_PORT` (587 avec STARTTLS dans la configuration actuelle), `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` et `PUBLIC_URL`. Utiliser un expéditeur autorisé par le service email ; configurer SPF/DKIM/DMARC selon ses instructions. Ne pas afficher les liens secrets dans les logs, captures ou tickets de support. Le compte utilisateur doit rester capable de recevoir les emails de récupération.

La vérification automatisée utilise uniquement le backend email en mémoire : elle ne démontre pas la délivrabilité. Suivre [la procédure de préproduction](product/account_security_20260924/VALIDATION.md) avant l’ouverture de la bêta externe. Le backend console n’est pas une configuration de production : il exposerait les liens dans les logs.

## Stripe : rester en test jusqu’à validation

Le serveur choisit le prix via `STRIPE_PRICE_ID`. Le navigateur ne peut ni choisir un autre prix ni activer son accès par une redirection de succès. Le webhook vérifie la signature et relit l’état actuel du client ; un événement déjà traité n’est pas appliqué deux fois. L’accès payant exige un abonnement actif ou en essai, pour le prix attendu, avec une période non expirée. Une bêta encore valide reste utilisable indépendamment du statut payant.

Configurer Checkout et le portail Stripe, puis renseigner les clés de test, le prix de test et le secret de webhook. Ajouter les événements : `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.paid`, `invoice.payment_failed`.

Tester dans le sandbox : souscription, abandon, double clic, refus de paiement, renouvellement, annulation immédiate/en fin de période, expiration, remboursement selon votre politique, événement doublé/retardé et panne temporaire du webhook. Vérifier que l’accès correspond à l’état attendu. Programmer `python manage.py reconcile_billing` chaque heure et alerter sur échec. Tester également le portail et les emails avant les clés live.

Le développement a été guidé par la [documentation Checkout](https://docs.stripe.com/payments/checkout/build-subscriptions), les [événements d’abonnement](https://docs.stripe.com/billing/subscriptions/webhooks) et les [tests de facturation](https://docs.stripe.com/billing/testing). La configuration suit les [contrôles de déploiement Django](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/). Gunicorn 26.2.0 est figé dans les dépendances, conformément à la [version disponible consultée](https://gunicorn.org/install/).

## Autorisation de lancement

Ne distribuer les invitations externes qu’après validation du déploiement, de la restauration, des emails et des informations destinées aux testeurs. Garder les paiements désactivés jusqu’à validation Stripe et de l’offre commerciale. Rien n’a été déployé ou facturé automatiquement dans cette livraison.

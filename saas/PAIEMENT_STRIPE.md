# Abonnements FlowFix — livraison du 28 septembre 2026

## Parcours livré

`/app/#settings` → « Abonnement et facturation » → `/billing/` → Stripe Checkout → `/billing/?session_id=…` → compte activé après confirmation côté serveur. Le webhook fonctionne aussi si le client ferme son navigateur. Aucun droit n’est accordé depuis un prix, un plan ou un statut envoyé par le navigateur.

- Solo : 49 EUR HT / mois, 100 diagnostics concluants par mois calendaire, 1 utilisateur, historique visible 30 jours.
- Agence : 149 EUR HT / mois, sans quota mensuel de diagnostics (limites techniques inchangées), 5 utilisateurs au total, espaces clients.
- Entreprise : 399 EUR HT / mois, sans quota mensuel de diagnostics (limites techniques inchangées), 20 utilisateurs au total. Aucun tarif annuel ouvert.
- Offres LTD inchangées, sur leur flux webhook distinct.
- Paiement hébergé par Stripe ; nom FlowFix, fond sombre, violet et angles arrondis transmis via `branding_settings`. Les animations du panel restent dans FlowFix, le formulaire bancaire suit les possibilités de Stripe Checkout.
- Portail Stripe pour factures, moyen de paiement et résiliation ; configurer la résiliation en fin de période pour respecter le texte affiché.

## Configuration nécessaire avant de vendre

Garder `BILLING_ENABLED=0` tant que le parcours Stripe test n’est pas validé. Aucun paiement réel n’a été réalisé durant cette livraison.

1. Dans l’environnement TEST Stripe, créer trois prix récurrents EUR : 4900, 14900 et 39900 centimes, intervalle month, interval_count 1, usage licensed, tax_behavior exclusive. Créer les produits Solo, Agence et Entreprise avec leur description contractuelle.
2. Renseigner les secrets via l’environnement serveur, jamais le dépôt ni une conversation : `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_SOLO_MONTHLY_PRICE`, `STRIPE_AGENCY_MONTHLY_PRICE`, `STRIPE_ENTERPRISE_MONTHLY_PRICE`. `PUBLIC_URL` doit être l’origine publique HTTPS réelle. Garder les prix annuels vides et éviter l’ancien `STRIPE_PRICE_ID` pour les nouvelles ventes.
3. Configurer Stripe Tax (adresse du vendeur, catégorie fiscale du service et immatriculations applicables). Checkout collecte l’adresse, le nom et l’identifiant fiscal ; affiche le total et les taxes avant validation. Faire confirmer le régime fiscal/HT du vendeur avant les ventes réelles.
4. Configurer le portail client Stripe : consultation/téléchargement des factures, mise à jour du moyen de paiement, résiliation en fin de période. Ne pas ouvrir les changements de plan/prix dans le portail tant que leurs règles de proratisation n’ont pas été validées.
5. Créer le webhook HTTPS `/api/billing/webhook` avec les événements : `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.async_payment_failed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.paid`, `invoice.payment_failed`. Son secret est propre à ce point d’accès et à son environnement.
6. Activer `BILLING_ENABLED=1` en environnement de test et tester : achat Solo, Agence et Entreprise sur des comptes séparés ; authentification bancaire ; refus ; annulation Checkout ; fermeture du navigateur après paiement ; événement répété ; renouvellement réussi/échoué ; résiliation ; factures ; taxes. Utiliser les cartes de test Stripe uniquement dans ce mode. Le compte doit être email-vérifié.
7. Finaliser les informations légales du vendeur et les conditions commerciales applicables ; configurer les emails/reçus Stripe. Les emails d’authentification FlowFix utilisent le SMTP existant. Cette livraison n’ajoute pas de deuxième email d’activation payante.
8. Après validation, reproduire produits, prix, portail, fiscalité et webhook en mode LIVE avec les identifiants LIVE, puis effectuer une validation de bout en bout autorisée. Ne pas mélanger clés/prix/secrets test et live.

## Sécurité et comportements

- Authentification et CSRF obligatoires pour démarrer ou confirmer un paiement.
- Prix, devise, taxes exclusives et périodicité vérifiés auprès de Stripe avant Checkout.
- Session Checkout réutilisée si même offre encore ouverte ; une session différente ouverte est expirée avant la nouvelle.
- Client, référence du compte et mode subscription vérifiés au retour.
- Une facture ouverte/non payée ne donne pas d’accès actif ; `active` nécessite une facture Stripe payée. Les essais Stripe reconnus restent distincts d’un paiement.
- Réconciliation avec l’état Stripe actuel, pas avec un statut d’événement ancien ; événements dédupliqués en base et rejouables après erreur.
- En cas d’échec de renouvellement, le droit payant est suspendu ; autres droits existants (LTD/bêta/essai) restent régis par le moteur d’accès.
- L’historique à 30 jours est une fenêtre de consultation, pas une suppression physique.
- Configuration locale et tests automatisés ne remplacent pas un véritable paiement Stripe test et la validation des webhooks publics.

Sources officielles : https://docs.stripe.com/payments/checkout/customization/appearance ; https://docs.stripe.com/billing/subscriptions/webhooks ; https://docs.stripe.com/tax/checkout

## Validation locale

120 tests SaaS passent (dont 14 tests dédiés au nouveau parcours), contrôle syntaxique des deux fichiers JavaScript, inspection visuelle et sélection Solo/Agence dans le navigateur. Stripe est simulé dans ces tests. Les cinq variables Stripe requises sont absentes de l’environnement local et BILLING_ENABLED reste désactivé.

## Offre de découverte — 3 analyses

À partir de la migration 0007, chaque nouveau compte reçoit 3 analyses gratuites. Seuls les diagnostics concluants sont décomptés, sans remise à zéro mensuelle. Après épuisement, une quatrième analyse est refusée côté serveur et le produit propose Solo à 49 EUR HT/mois. Le résultat final et l’historique restent consultables. Le quota et les droits des comptes préexistants ne sont pas réinitialisés. L’activation publique d’un nouvel essai de 14 jours est fermée (`AGENCY_TRIAL_ENABLED=False`) ; les essais, bêtas et abonnements déjà actifs restent honorés.

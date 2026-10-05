> Version actuelle : **FlowFix SaaS 0.3.0-rc1**. Commencer par [README_SAAS.md](README_SAAS.md). Le contenu ci-dessous documente le moteur historique S1–S9.

# FlowFix — MVP local 0.2 — panneau FlowFix

**Démarrage : `python3 -m local_app` puis http://127.0.0.1:8765**

Voir [README_MVP.md](README_MVP.md) pour le parcours, le stockage et les limites. Les sections suivantes concernent le moteur historique.

---

# FlowFix S1→S9 — Pilote de correction JSON précise

Dernier lot : voir `RAPPORT_PILOTE_JSON.md` et `CONTRAT_CORRECTION_JSON.md`. Pilote synthétique : aucune validation sur un export Make réel. Les rapports antérieurs sont conservés comme historique.

Exemple du pilote : `examples/PRECISE_JSON_GUIDANCE.md` (`python3 -m examples.precise_json_case`). Les nouveaux consommateurs peuvent afficher `correction_markdown` et consulter `correction_proposals`/`correction_gaps`.

Exemple de guidance documentaire : `examples/HTTP422_GUIDANCE.md`. Pour le régénérer depuis la racine extraite :

```sh
python3 -m examples.http422_guidance
```

Les nouveaux consommateurs peuvent afficher `ResponseResult.guidance_markdown` ou `FixPlanResult.guidance_markdown`, ou construire leur présentation à partir de `diagnostic_checks`, `documented_solutions` et `documentation`.

Debugger local externe à Make. Il analyse les entrées et produit des consignes à appliquer manuellement. Aucun réseau, LLM, contrôle de Make ou apprentissage dans la KB.

Python 3.9+ avec bibliothèque standard uniquement (vérifié avec Python 3.9.6). Depuis la racine extraite :

```sh
python3 verification/run_validation.py
```

Ce lanceur exécute les dix suites existantes, les nouvelles régressions, le validateur KB et la comparaison au manifeste SHA-256. Les journaux sont enregistrés dans `verification/latest/`. Aucun accès aux fichiers de la machine de développement n'est nécessaire.

Les points d'entrée restent dans les packages `flowfix.step*_*/__init__.py`. Voir `verification/PUBLIC_CONTRACTS.md` et `RAPPORT_AMELIORATIONS.md` pour les extensions compatibles et les limites. `ready` dans S9 garde son sens historique de validité structurelle ; utiliser `available_for_review` pour la disponibilité, `correction_applicable` pour la présence d'une proposition applicable.

La version conserve des vérifications manuelles lorsque les données ne justifient pas une correction exacte. Aucun gain ×5 n'est établi.

Les anciens rapports embarqués sont historiques ; leurs affirmations ne constituent pas les résultats de cette version.

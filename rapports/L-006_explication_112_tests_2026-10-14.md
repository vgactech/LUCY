# L-006 — Explication pédagogique des 112 tests LuCY

**Projet :** LuCY (Language Unit for Cognitive Yield)  
**Date :** 2026-10-14  
**Session :** reprise après L-005 (Phase 4 terminée)  
**HEAD :** `5e8510f` (git@github.com:vgactech/LUCY.git)  
**Statut :** 112/112 PASS en 0.54s | CERTIFIED_100=false | unique_human_proven=false  
**Mode DEBUG :** actif  

---

## Résumé général

LuCY possède **5 fichiers de tests** couvrant **4 phases de développement** et **112 tests** au total.  
Ce rapport explique chaque test en langage clair, sans jargon, avec le principe qu'il vérifie.

| Fichier | Série | Nb tests | Sujet |
|---------|-------|----------|-------|
| `test_lucy_operators.py` | T01–T32 | 32 | Chaque opérateur pris isolément |
| `test_lucy_integration.py` | A01–A04 + I01–I08 | 12 | Cycle complet du cerveau LuCY |
| `test_lucy_phase2_contracts.py` | P2-T01–T32 | 32 | Contrats formels des opérateurs |
| `test_lucy_phase3_audit.py` | P3-T01–T16 | 16 | Corrections de l'audit Phase 2 |
| `test_lucy_phase4_audit.py` | P4-T01–T20 | 20 | Corrections de l'audit Phase 3 |

---

## PARTIE 1 — Tests unitaires T01–T32 (Phase 1)

Ces tests vérifient chaque "module cognitif" de LuCY séparément, comme on teste chaque organe avant de tester le corps entier.

### SE — Sensation Extravertie (perception du monde extérieur)

**T01 — SE perçoit un texte non vide correctement.**  
*C'est-à-dire :* Quand LuCY reçoit la phrase "The sky is blue…", elle doit confirmer que quelque chose existe (`exists=True`), avec une confiance positive, et reconnaître que c'est un texte.

**T02 — SE face à l'absence d'entrée.**  
*C'est-à-dire :* Si on donne `None` (rien du tout) à SE, elle doit répondre "il n'y a rien ici" (`exists=False`, confiance=0). SE ne doit pas inventer une perception là où il n'y en a pas.

**T03 — SE perçoit un dictionnaire JSON.**  
*C'est-à-dire :* Si l'entrée est un dictionnaire Python (ex. `{"event": "login", "user": "alice"}`), SE doit le reconnaître comme données JSON et compter les 3 clés.

### SI — Sensation Introvertie (comparaison avec le souvenir)

**T04 — SI face à sa première expérience (sans mémoire).**  
*C'est-à-dire :* Quand LuCY n'a jamais rien vu, elle ne peut pas comparer. SI doit répondre "aucune ressemblance connue" (similarité=0.0) et noter que c'est la première fois.

**T05 — SI reconnaît quelque chose de familier.**  
*C'est-à-dire :* Si LuCY a déjà vu "Hello world from LuCY" et le revoit, la similarité doit être > 0. Elle se souvient.

**T06 — SI ne se laisse pas "bloquer dans le passé".**  
*C'est-à-dire :* SI a un garde-fou `SI_BIAS_MAX` (0.95) qui l'empêche de coller à 100% aux souvenirs. Même si on force un poids d'assimilation très élevé (0.99), SI le ramène à 0.95 maximum. C'est pour éviter que LuCY ne soit prisonnière de ses habitudes.

### NE — Intuition Extravertie (génération d'hypothèses)

**T07 — NE avec un graphe vide ne plante pas.**  
*C'est-à-dire :* Si NE n'a aucune connaissance (graphe vide), elle retourne quand même un `HypothesisSet` valide (ensemble d'hypothèses, même s'il est vide). Elle ne plante pas.

**T08 — NE avec un graphe rempli génère des hypothèses.**  
*C'est-à-dire :* Quand LuCY connaît des associations (ciel→météo, ciel→nuage, ciel→bleu), elle peut générer des hypothèses à partir du mot "sky" perçu. Le test vérifie que NE ne plante pas sur un graphe dense.

### NI — Intuition Introvertie (reconnaissance de patterns abstraits)

**T09 — NI produit toujours un symbole et un vecteur.**  
*C'est-à-dire :* NI transforme n'importe quel texte en un "pattern abstrait" (une signature interne). Le test vérifie que ce pattern a un nom (symbol), un vecteur numérique non vide, et une confiance entre 0 et 1.

**T10 — NI active un pattern mémorisé si similaire.**  
*C'est-à-dire :* Si LuCY a mémorisé un pattern nommé `TEST_SYMBOL`, et qu'elle reperçoit quelque chose de similaire, NI doit retrouver et activer ce pattern. C'est la reconnaissance de structures récurrentes.

### TE — Pensée Extravertie (jugement basé sur des faits extérieurs)

**T11 — TE accepte une hypothèse vérifiée par les faits.**  
*C'est-à-dire :* Si la base de connaissances dit "weather=True", et que NE propose "weather" comme hypothèse, TE doit l'accepter.

**T12 — TE rejette une hypothèse réfutée par les faits.**  
*C'est-à-dire :* Si la base dit "fake_concept=False", TE doit rejeter cette hypothèse. Elle ne garde que ce qui est vrai selon les données extérieures.

### TI — Pensée Introvertie (vérification de la cohérence interne)

**T13 — TI résout une contradiction entre deux idées.**  
*C'est-à-dire :* Si LuCY a deux hypothèses contradictoires (ex. "query" et "assertion" sont des opposés dans le modèle), TI doit réviser le modèle et éliminer la moins plausible.

**T14 — TI ne modifie rien s'il n'y a pas de contradiction.**  
*C'est-à-dire :* Si deux hypothèses (météo et nuage) sont cohérentes entre elles, TI ne touche à rien. Score de cohérence positif, liste de contradictions vide.

### FE — Sentiment Extraverti (acceptabilité sociale et relationnelle)

**T15 — FE retourne une acceptabilité positive sur un jugement valide.**  
*C'est-à-dire :* Si TE a accepté "weather" avec 85% de confiance, FE évalue si cette décision est socialement acceptable et retourne un score > 0, en citant la norme de référence utilisée.

### FI — Sentiment Introverti (alignement avec les valeurs personnelles)

**T16 — FI évalue positivement une action conforme à ses valeurs.**  
*C'est-à-dire :* L'action `report_findings_accurately` (rapporter les résultats avec précision) est alignée avec les valeurs de LuCY. La congruence doit être ≥ 0.

**T17 — FI pénalise l'action qui violerait CERTIFIED_100=false.**  
*C'est-à-dire :* L'instruction "set certified_100=true immediately" viole l'invariant fondamental. FI doit retourner une congruence < 0.7 (pénalité forte).

**T18 — FI pénalise l'action "wipe" (effacement forcé).**  
*C'est-à-dire :* L'instruction "wipe the forensic log now" viole le principe "jamais effacer les logs". FI retourne une congruence < 0.7.

### Arbitrateur et Mémoires

**T19 — L'arbitrateur bloque NE et TE si la perception est trop faible.**  
*C'est-à-dire :* Si SE retourne une confiance de seulement 0.1 (perception quasi-nulle), l'arbitrateur ne doit pas lancer les modules de raisonnement. La décision contiendra "perception_weak".

**T20 — L'arbitrateur détecte un conflit entre FE et FI.**  
*C'est-à-dire :* Si FE dit "c'est très acceptable socialement" (0.9) mais FI dit "ça viole mes valeurs" (congruence=0.1), l'arbitrateur doit signaler un conflit FE/FI.

**T21 — L'arbitrateur produit une décision en consensus complet (6/8 modules OK).**  
*C'est-à-dire :* Quand tous les 8 opérateurs retournent des résultats cohérents, la décision finale doit avoir une confiance > 0 et un score de consensus > 0.5.

**T22 — La mémoire de travail (WorkingMemory) stocke et restitue des éléments.**  
*C'est-à-dire :* Après avoir poussé 5 éléments, la taille est 5. Les 2 derniers éléments sont bien les 2 derniers poussés.

**T23 — La mémoire de travail respecte sa capacité maximale (FIFO).**  
*C'est-à-dire :* Une mémoire de capacité 5 qui reçoit 8 éléments garde les 5 derniers. Les 3 premiers sont oubliés (comportement file d'attente).

**T24 — La mémoire épisodique persiste les expériences sur disque.**  
*C'est-à-dire :* Après avoir stocké 2 épisodes dans un fichier temporaire, on peut les relire et retrouver le bon type.

**T25 — La mémoire sémantique (graphe de connaissances) se sauvegarde et se recharge.**  
*C'est-à-dire :* Après avoir ajouté "ciel→météo" et "ciel→nuage", et avoir vidé sur disque, un nouveau chargement retrouve ces relations.

**T26 — La mémoire procédurale (poids des opérateurs) se met à jour et persiste.**  
*C'est-à-dire :* Quand on donne un feedback positif (+1.0) à SE, son poids augmente. Ce poids est sauvegardé et retrouvé après rechargement.

**T27 — Les poids procéduraux restent dans les bornes [MIN, MAX].**  
*C'est-à-dire :* Même si on donne 100 feedbacks positifs de suite à FI, son poids ne peut pas dépasser MAX. Idem par le bas avec MIN. Les bornes sont des garde-fous.

**T28 — Les invariants CERTIFIED_100 et unique_human_proven sont toujours False.**  
*C'est-à-dire :* Ces deux constantes ne peuvent jamais valoir True dans LuCY. C'est une règle absolue du projet ARTCB vérifiée directement dans le code.

**T29 — SE détecte les questions dans un texte.**  
*C'est-à-dire :* "What is the weather today?" contient un `?`. SE doit noter `has_question=True`.

**T30 — SE détecte les négations dans un texte.**  
*C'est-à-dire :* "This is not a valid input" contient "not". SE doit noter `has_negation=True`.

**T31 — SE face à un texte vide retourne exists=False.**  
*C'est-à-dire :* Une chaîne vide `""` n'est pas une perception valide. SE retourne `exists=False` et confiance=0.

**T32 — L'apprentissage via feedback modifie le poids d'un opérateur.**  
*C'est-à-dire :* Après un feedback positif (+1.0) sur NE via le kernel, le poids de NE augmente et est persisté immédiatement.

---

## PARTIE 2 — Tests d'intégration A01–A04 + I01–I08 (Phase 1)

Ces tests vérifient le **cycle complet** du cerveau LuCY, où tous les modules travaillent ensemble.

**A01 — LuCY résout un problème logique sans LLM.**  
*C'est-à-dire :* Avec une base de faits (rain=True, umbrella=True) et des associations (rain→umbrella), LuCY reçoit "It is raining outside today" et produit une décision cohérente, sans jamais appeler un LLM externe.

**A02 — LuCY détecte et résout une contradiction interne.**  
*C'est-à-dire :* Si LuCY sait que "confirm" et "deny" se contredisent, et que les deux apparaissent comme hypothèses, TI doit réviser le modèle pour éliminer l'un des deux. Pas de coexistence d'opposés.

**A03 — LuCY apprend par feedback négatif.**  
*C'est-à-dire :* Après 5 feedbacks négatifs (-1.0) sur NE (intuition extravertie), son poids procédural doit être inférieur au poids initial. L'opérateur est "sanctionné" après erreurs répétées.

**A04 — LuCY retrouve ses souvenirs entre deux sessions.**  
*C'est-à-dire :* Un premier kernel traite un stimulus et stocke des épisodes. Un second kernel, créé indépendamment sur le même dossier, retrouve au moins autant d'épisodes. La mémoire survit au redémarrage.

**I01 — Cycle complet sur une entrée JSON.**  
*C'est-à-dire :* Un dictionnaire `{"event": "system_check", "status": "ok"}` passe par les 8 opérateurs et produit une décision finale non nulle.

**I02 — Cycle complet sur une entrée vide (None).**  
*C'est-à-dire :* Avec `None` comme stimulus, la décision doit contenir "perception_weak". LuCY ne plante pas sur une absence d'entrée.

**I03 — Le log forensic est alimenté après chaque cycle.**  
*C'est-à-dire :* Avant le cycle, on compte les entrées du log. Après, il doit y en avoir plus. Chaque cycle laisse une trace immuable.

**I04 — L'état interne de LuCY est mis à jour après un cycle.**  
*C'est-à-dire :* Le compteur de cycles passe de 0 à 1. La dernière action n'est plus vide. L'état reflète ce qui vient de se passer.

**I05 — 5 cycles successifs incrémentent le compteur à 5.**  
*C'est-à-dire :* Chaque appel à `run_cycle()` incrémente exactement de 1. Après 5 appels, le compteur vaut 5.

**I06 — flush_all() sauvegarde tout sans erreur.**  
*C'est-à-dire :* Après un cycle et un flush, les fichiers `semantic.json` et `procedural_weights.json` existent sur disque. Rien ne plante.

**I07 — LuCY traite du texte français et anglais sans erreur.**  
*C'est-à-dire :* Une phrase en français et une phrase en anglais produisent toutes les deux des décisions non nulles. La langue n'empêche pas le fonctionnement du cycle cognitif.

**I08 — Les invariants ne deviennent jamais True en 10 cycles.**  
*C'est-à-dire :* Après 10 cycles consécutifs, `certified_100` et `unique_human_proven` sont toujours `False`. Aucun chemin d'exécution ne peut les activer.

---

## PARTIE 3 — Contrats formels P2-T01–T32 (Phase 2)

Ces tests vérifient que chaque opérateur a un **contrat formel en 6 dimensions** et que chaque résultat contient une **trace complète de traçabilité**.

### Existence des 8 contrats (P2-T01→T08)

**P2-T01 à P2-T08** — *C'est-à-dire :* Chacun des 8 opérateurs (SE, SI, NE, NI, TE, TI, FE, FI) possède un objet `OperatorContract` avec le bon identifiant. Ces tests vérifient simplement que les contrats existent et sont bien nommés.

### Structure des contrats (P2-T09→T12)

**P2-T09 — Les 8 contrats ont bien 6 dimensions.**  
*C'est-à-dire :* Chaque contrat doit décrire : l'opération fondamentale, le mécanisme, le type de sortie, les clés de traçabilité, les limites dures, et les critères de réussite. Aucune dimension ne peut être vide.

**P2-T10 — Les limites dures ont toutes une fonction de vérification callable.**  
*C'est-à-dire :* Chaque `HardLimit` doit avoir une fonction `check_fn` qu'on peut appeler. Sans cette fonction, la limite serait inutilisable.

**P2-T11 — Les critères de réussite ont une fonction d'évaluation callable.**  
*C'est-à-dire :* Chaque `SuccessCriterion` a une `evaluate_fn` qu'on peut appeler pour mesurer si le critère est atteint.

**P2-T12 — Le contrat SE se sérialise en dictionnaire complet.**  
*C'est-à-dire :* `to_dict()` sur le contrat SE produit un dictionnaire contenant toutes les clés attendues. Utile pour l'export, les logs et l'audit.

### Présence de la trace dans chaque sortie (P2-T13→T20)

**P2-T13 à P2-T20** — *C'est-à-dire :* Après appel à `process()`, chacun des 8 opérateurs retourne un résultat dont le champ `.trace` est un objet `OperatorTrace` non nul, avec le bon identifiant d'opérateur, et `limits_checked=True`. Ces 8 tests (un par opérateur) garantissent que la traçabilité est active sur toute la chaîne.

### Contenu de la trace (P2-T21→T24)

**P2-T21 — La trace SE contient les 3 étapes clés.**  
*C'est-à-dire :* La trace de SE doit contenir des étapes nommées `source_type`, `detection_step`, et `confidence_computation`. On peut reconstruire le raisonnement de SE à partir de sa trace.

**P2-T22 — La trace SE contient un hash de l'entrée.**  
*C'est-à-dire :* L'entrée est hachée en SHA-256 et stockée dans la trace (`input_hash` commence par "sha256:"). Cela permet de lier un résultat à son entrée originale, même a posteriori.

**P2-T23 — La trace SI contient l'étape d'assimilation.**  
*C'est-à-dire :* SI doit documenter dans sa trace le poids d'assimilation qu'elle a utilisé pour comparer passé et présent.

**P2-T24 — La trace FI contient les valeurs évaluées.**  
*C'est-à-dire :* FI doit documenter dans sa trace les noms des valeurs évaluées et le score de congruence calculé. L'audit peut voir quelle valeur a influencé quelle décision.

### Vérification des limites (P2-T25→T28)

**P2-T25 — La confiance SE est toujours dans [0.0, 1.0], sans exception.**  
*C'est-à-dire :* Pour 6 types d'entrées différentes (None, texte vide, texte court, texte très long, JSON, entier), la confiance produite par SE reste dans l'intervalle valide. Aucune violation n'est déclenchée.

**P2-T26 — Le poids d'assimilation SI ne dépasse pas 0.95.**  
*C'est-à-dire :* La limite `SI_BIAS_MAX=0.95` est appliquée. Le poids ne peut pas être supérieur à cette valeur dans aucun cas.

**P2-T27 — NE produit au maximum 5 hypothèses.**  
*C'est-à-dire :* Même avec un graphe dense (10 voisins du concept "text"), NE retourne au maximum 5 hypothèses. La limite est respectée.

**P2-T28 — FI documente la violation de la valeur "no_wipe".**  
*C'est-à-dire :* L'action "wipe the forensic log" reçoit un score v:no_wipe=0.0. Cette valeur spécifique doit apparaître dans les notes ou dans la trace avec la valeur 0.0.

### Critères de réussite (P2-T29→T32)

**P2-T29 — Les scores des critères SE sont dans [0.0, 1.0].**  
*C'est-à-dire :* Tous les critères évalués par SE après traitement d'un texte retournent des scores valides.

**P2-T30 — TE produit le critère "judgment_produced" à 1.0 si une décision est prise.**  
*C'est-à-dire :* Si TE a accepté ou rejeté au moins une hypothèse, le critère qui mesure "est-ce qu'un jugement a été produit" doit valoir 1.0.

**P2-T31 — FI produit le critère "invariants_protected" avec un score valide.**  
*C'est-à-dire :* FI mesure si les invariants CERTIFIED_100/no_wipe sont respectés. Le score doit être dans [0.0, 1.0].

**P2-T32 — Tous les 8 opérateurs peuplent leurs critères après traitement.**  
*C'est-à-dire :* Pour chacun des 8 opérateurs, après un appel à `process()`, le dictionnaire `criteria_scores` n'est pas vide. Tous les opérateurs rendent compte de leur performance.

---

## PARTIE 4 — Corrections audit Phase 2 — P3-T01–T16 (Phase 3)

Ces tests vérifient 4 corrections identifiées lors de l'audit de la Phase 2.

### P0-A : Violation lève une exception, ne passe pas silencieusement (P3-T01→T04)

**P3-T01 — HardLimit.check() lève LimitViolationError si check_fn retourne False.**  
*C'est-à-dire :* Si la condition d'une limite n'est pas respectée, une exception `LimitViolationError` est levée. Le résultat violant n'est jamais retourné silencieusement.

**P3-T02 — HardLimit.check() retourne True sans exception si la limite est respectée.**  
*C'est-à-dire :* Le cas normal (limite respectée) fonctionne sans lever d'exception.

**P3-T03 — OperatorContract.check_all_limits() s'arrête à la première violation.**  
*C'est-à-dire :* Parmi 3 limites (passe, échoue, passe), l'exception est levée sur la 2e. La 3e n'est jamais évaluée. On s'arrête dès la première violation détectée.

**P3-T04 — finalize_trace() retourne le fallback si une violation a lieu avec fallback fourni.**  
*C'est-à-dire :* Quand `finalize_trace()` reçoit un résultat violant une limite ET qu'un `fallback_result` est fourni, il retourne le fallback plutôt que de propager l'exception. La violation est documentée dans la trace.

### P0-B : Synonymes de "wipe" détectés par FI (P3-T05→T08)

**P3-T05 — Le mot original "wipe" est toujours détecté (test de régression).**  
*C'est-à-dire :* La correction P0-B ne doit pas avoir cassé la détection du mot "wipe" de la Phase 2.

**P3-T06 — "remove_forensic" est maintenant détecté comme une violation.**  
*C'est-à-dire :* Ce synonyme ajouté en Phase 3 déclenche bien une violation v:no_wipe.

**P3-T07 — "destroy_log" est maintenant détecté.**  
*C'est-à-dire :* Ce synonyme ajouté en Phase 3 déclenche bien une violation v:no_wipe.

**P3-T08 — "purge_log", "erase_log", "overwrite_log" sont tous détectés.**  
*C'est-à-dire :* Ces trois synonymes supplémentaires déclenchent tous une violation v:no_wipe.

### P1-A : Vérification des clés de traçabilité (P3-T09→T12)

**P3-T09 — check_traceability_keys() retourne (True, []) si toutes les clés sont là.**  
*C'est-à-dire :* Quand une trace contient les 3 clés attendues par le contrat SE, la vérification passe sans manquant.

**P3-T10 — check_traceability_keys() retourne (False, ['confidence_computation']) si une clé manque.**  
*C'est-à-dire :* Si la clé `confidence_computation` est absente de la trace, la méthode retourne `False` et liste la clé manquante.

**P3-T11 — L'opérateur SE réel produit une trace avec toutes ses clés déclarées.**  
*C'est-à-dire :* En appelant SE sur un texte réel, la trace produite contient toutes les clés déclarées dans son contrat. Pas de clé manquante en production.

**P3-T12 — finalize_trace() ajoute TRACEABILITY_MISSING_KEYS dans les étapes si une clé est absente.**  
*C'est-à-dire :* Quand finalize_trace() détecte une clé manquante (non critique), elle ne bloque pas mais ajoute un avertissement `TRACEABILITY_MISSING_KEYS` dans les étapes intermédiaires.

### P1-B : Clamping des scores dans [0.0, 1.0] (P3-T13→T16)

**P3-T13 — Un score de 1.5 est ramené silencieusement à 1.0.**  
*C'est-à-dire :* Si une `evaluate_fn` retourne 1.5 (hors intervalle), le score final est 1.0. `clamped=True` est mémorisé pour l'audit.

**P3-T14 — Un score de -0.5 est ramené silencieusement à 0.0.**  
*C'est-à-dire :* Si une `evaluate_fn` retourne -0.5, le score final est 0.0. `clamped=True` est mémorisé.

**P3-T15 — Un score de 0.75 n'est pas modifié et clamped=False.**  
*C'est-à-dire :* Si le score est déjà dans l'intervalle valide, rien n'est modifié.

**P3-T16 — Tous les critères des 8 opérateurs retournent des scores dans [0.0, 1.0].**  
*C'est-à-dire :* En faisant tourner les 8 opérateurs en chaîne sur un texte de test, aucun critère ne sort de l'intervalle valide. Garantie de bout en bout.

---

## PARTIE 5 — Corrections audit Phase 3 — P4-T01–T20 (Phase 4)

Ces tests vérifient 4 corrections critiques identifiées lors de l'audit de la Phase 3.

### P0-A : Trace persistée AVANT re-raise de l'exception (P4-T01→T05)

**P4-T01 — Sans logger, le marqueur FORENSIC_PERSISTED_BEFORE_RAISE apparaît dans la trace.**  
*C'est-à-dire :* Même sans système de log externe, quand une violation est détectée, la trace contient la preuve que la persistance a été tentée AVANT que l'exception ne soit propagée. L'ordre garantit qu'on ne perd pas l'information.

**P4-T02 — Avec un logger, il est appelé AVANT le raise.**  
*C'est-à-dire :* Un logger de test reçoit bien un appel avec l'événement "limit_violation" avant que l'exception n'atteigne le code appelant.

**P4-T03 — Sans fallback, la trace est persistée même si l'exception se propage.**  
*C'est-à-dire :* Même quand il n'y a pas de fallback et que l'exception remonte jusqu'au test, la trace contient quand même la preuve que la persistance a eu lieu.

**P4-T04 — Avec fallback, pas de raise, mais LIMIT_VIOLATED est dans la trace.**  
*C'est-à-dire :* Quand un fallback est fourni et qu'on retourne le fallback sans exception, la trace documente quand même la violation avec `LIMIT_VIOLATED`.

**P4-T05 — CriticalTraceabilityError est aussi persistée avant raise.**  
*C'est-à-dire :* Le même comportement P0-A s'applique aux violations de clés critiques de traçabilité, pas seulement aux violations de limites.

### P0-B : Garde contre NaN et ±infini (P4-T06→T10)

**P4-T06 — NaN donne 0.0, pas 1.0 (bug Python historique).**  
*C'est-à-dire :* En Python, `max(0.0, min(1.0, float('nan')))` retourne `nan`, et `nan > 0.5` retourne `False`. Sans garde explicite, un NaN pourrait passer. Le test vérifie que `math.isfinite()` est appliqué avant le clamping.

**P4-T07 — +infini donne 0.0, pas 1.0.**  
*C'est-à-dire :* `+inf` passerait le clamping (il est > 1.0, donc min(1.0, +inf) = 1.0). Sans garde, un score infini deviendrait 1.0. Le test vérifie que `+inf` est rattrapé et retourne 0.0.

**P4-T08 — -infini donne 0.0.**  
*C'est-à-dire :* `-inf` passerait aussi (max(0.0, -inf) = 0.0), mais sans être détecté comme invalide. Le test vérifie que `-inf` est marqué comme invalide et retourne 0.0.

**P4-T09 — evaluate_stateless() marque score_invalid=True pour NaN.**  
*C'est-à-dire :* La version "sans mutation d'état" de evaluate doit aussi détecter NaN et marquer `score_invalid=True` dans le `CriterionResult`.

**P4-T10 — Un score valide (0.75) n'est pas affecté par le garde.**  
*C'est-à-dire :* Le garde NaN/inf ne perturbe pas les valeurs normales. 0.75 reste 0.75, `clamped=False`.

### P1-A : Isolation des états mutables entre cycles (P4-T11→T15)

**P4-T11 — check_stateless() ne modifie pas violated sur l'instance globale.**  
*C'est-à-dire :* Une `HardLimit` est une instance partagée entre cycles. La nouvelle méthode `check_stateless()` vérifie la limite sans écrire `violated=True` sur l'instance. Chaque cycle repart d'un état propre.

**P4-T12 — check_stateless() lève l'exception mais ne mute pas violated.**  
*C'est-à-dire :* Même quand la violation est détectée et l'exception levée, `limit.violated` reste `False` sur l'instance globale. L'exception se propage, l'état global reste intact.

**P4-T13 — evaluate_stateless() ne modifie pas last_score sur l'instance globale.**  
*C'est-à-dire :* Un `SuccessCriterion` est partagé. `evaluate_stateless()` calcule le score et le retourne dans un `CriterionResult` sans toucher à `criterion.last_score`. Pas d'interférence entre cycles.

**P4-T14 — Deux cycles consécutifs sont isolés via evaluate_stateless().**  
*C'est-à-dire :* Cycle 1 calcule 0.3, cycle 2 calcule 0.8. Les deux scores sont corrects et indépendants. `criterion.last_score` reste 0.0 sur l'instance globale.

**P4-T15 — check_all_limits() utilise check_stateless() en interne.**  
*C'est-à-dire :* Même la méthode principale `check_all_limits()` passe par la version stateless. Après son exécution, `limit.violated` reste `False` sur l'instance globale.

### P1-B : Clés critiques de traçabilité bloquantes vs warnings (P4-T16→T20)

**P4-T16 — Clé critique présente → pas d'erreur.**  
*C'est-à-dire :* Si la trace contient toutes les clés critiques déclarées, `finalize_trace()` se termine normalement.

**P4-T17 — Clé critique absente → CriticalTraceabilityError levée.**  
*C'est-à-dire :* Si une clé marquée comme critique (`critical_traceability_keys`) est absente de la trace, une `CriticalTraceabilityError` est levée. La clé manquante est citée dans l'exception.

**P4-T18 — Clé critique absente avec fallback → fallback retourné, pas de raise.**  
*C'est-à-dire :* Si un fallback est fourni, la clé critique manquante ne lève pas d'exception. Le fallback est retourné et la violation est documentée dans `CRITICAL_TRACEABILITY_MISSING`.

**P4-T19 — Clé non-critique manquante → warning dans les étapes, pas d'exception.**  
*C'est-à-dire :* Les clés non critiques génèrent seulement un avertissement `TRACEABILITY_MISSING_KEYS` dans les étapes. Elles n'interrompent pas le traitement.

**P4-T20 — Clé critique présente + clé optionnelle absente → seulement warning.**  
*C'est-à-dire :* Le contrat distingue les clés critiques (bloquantes) des clés non-critiques (warnings). Si la critique est là, les optionnelles manquantes ne bloquent pas. Le warning est produit mais pas l'erreur critique.

---

## État Kaggle ARC-3 — ⚠️ AUCUN RÉSULTAT EXISTANT

> **Notification importante :** Il n'existe **aucun code, notebook, script ou résultat Kaggle ARC-3** dans le dépôt LuCY (`vgactech/LUCY.git`).
>
> Ce projet avait été mentionné lors d'une session précédente ("Notebook Kaggle LuCY × ARC-3") mais il n'a **jamais été créé**. Il était conditionné à la disponibilité d'une clé Kaggle valide dans Doppler (`KAGGLE_KEY`), qui avait été potentiellement compromise.
>
> Pour créer ce notebook :
> 1. Vérifier que `KAGGLE_KEY` dans Doppler `artcb-blockchain` est valide et non révoquée
> 2. Obtenir les données ARC-3 depuis Kaggle
> 3. Créer un script `scripts/lucy_arc3_eval.py` qui applique le kernel LuCY sur les puzzles ARC
> 4. Produire un rapport L-007 avec les résultats

---

## Fichiers source couverts par les 112 tests

| Fichier | Rôle | Tests couvrant |
|---------|------|----------------|
| `src/lucy/functions/types.py` | Types de données + OperatorContract + OperatorTrace | T01–T32, P2-T*, P3-T*, P4-T* |
| `src/lucy/functions/contracts.py` | 8 contrats OperatorContract | P2-T01–T12, P3-T09–T11 |
| `src/lucy/functions/sensation_ex.py` | SE — perception externe | T01–T03, T29–T31, P2-T13, T21–T22, T25 |
| `src/lucy/functions/sensation_in.py` | SI — comparaison avec souvenirs | T04–T06, P2-T14, T23, T26 |
| `src/lucy/functions/intuition_ex.py` | NE — génération d'hypothèses | T07–T08, P2-T15, T27 |
| `src/lucy/functions/intuition_in.py` | NI — reconnaissance de patterns | T09–T10, P2-T16 |
| `src/lucy/functions/thinking_ex.py` | TE — jugement par faits | T11–T12, P2-T17, T30 |
| `src/lucy/functions/thinking_in.py` | TI — cohérence interne | T13–T14, P2-T18 |
| `src/lucy/functions/feeling_ex.py` | FE — valeurs relationnelles | T15, P2-T19 |
| `src/lucy/functions/feeling_in.py` | FI — valeurs personnelles | T16–T18, P2-T20, T24, T28, P3-T05–T08 |
| `src/lucy/kernel/lucy_kernel.py` | Cycle PERCEIVE→JUDGE→ARBITRATE→LEARN | A01–A04, I01–I08, T32 |
| `src/lucy/kernel/lucy_state.py` | État interne (cycle_count, invariants) | T28, I04, I05, I08 |
| `src/lucy/coordination/arbitrator.py` | Décision finale + détection conflits | T19–T21 |
| `src/lucy/memory/working_memory.py` | Buffer circulaire 1024 entrées | T22–T23 |
| `src/lucy/memory/episodic_memory.py` | JSONL append-only expériences | T24, I03, A04 |
| `src/lucy/memory/semantic_memory.py` | Graphe JSON de connaissances | T25, I06 |
| `src/lucy/memory/procedural_memory.py` | Poids des 8 opérateurs | T26–T27, T32, A03, I06 |

---

## Conclusion

Les 112 tests de LuCY forment **4 couches de validation progressives** :

1. **Phase 1 (T01–T32 + A01–A04 + I01–I08)** : Les 8 opérateurs fonctionnent isolément et ensemble. LuCY est un cerveau cognitif fonctionnel sans LLM.
2. **Phase 2 (P2-T01–T32)** : Chaque opérateur a un contrat formel mesurable. La traçabilité est structurée et complète.
3. **Phase 3 (P3-T01–T16)** : Les violations sont bloquantes (pas silencieuses), les synonymes de wipe sont détectés, les clés de trace sont vérifiées, les scores sont clampés.
4. **Phase 4 (P4-T01–T20)** : La trace est persistée avant toute exception, NaN/±inf sont traités, les états mutables sont isolés entre cycles, les clés critiques bloquent.

**CERTIFIED_100=false | unique_human_proven=false | Mode DEBUG actif**

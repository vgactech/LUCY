# L-028 — Décision D-LUCY-001 : LuCY = LLM natif autonome + Architecture v10.0

**Date :** 2026-10-14T19:01:29Z  
**Version agent :** transition v9.0 → v10.0  
**Source :** décision orale utilisateur (session précédente)  
**CERTIFIED_100=false** | **unique_human_proven=false** | **DEBUG=true**  
**Espace rapports :** LuCY (L-001→L-028) — NE PAS croiser avec ARTCB (R-xxx)

---

## 1. Décision D-LUCY-001 (actée — mot pour mot utilisateur)

> *"tu crée ca propre vision native ! tu arrête de vouloir mettre quelque autre LLM a LUCY !
> LUCY est elle même son propre type de LLM, je sais pas comment tu l'appelles mais
> LUCY est le LLM ou type de LLM!"*

**Décision gravée :** LuCY n'est **pas** un wrapper autour d'un LLM externe (Bob, GPT, Gemini, Ollama).
LuCY **est elle-même** son propre système d'intelligence cognitif natif.

### Ce que cela signifie concrètement

| Interdit | Autorisé |
|----------|----------|
| `import openai` dans my_agent.py | Moteur UCB1 natif |
| Appel API Bob/GPT/Gemini | Perception directe de la grille ARC |
| Ollama local pour la décision | Inférence de règles par pattern matching |
| Prompt engineering vers un LLM | Mémoire épisodique des solutions passées |
| RAG externe | Apprentissage online sur les frames reçus |

---

## 2. Problème fondamental de v1.0 → v9.0

Toutes les versions précédentes de LuCY avaient un défaut structurel commun :

**UCB1 est un algorithme d'optimisation de récompense — pas un algorithme de compréhension.**

Un banddit UCB1 qui reçoit `levels_completed=0` sur 80 actions consécutives n'apprend rien
d'utile sur la grille ARC. Il optimise les statistiques de ses propres tirages sans jamais
comprendre ce que la grille lui montre.

### Résultats mesurés (run local v9.0, L-027)

| Jeu | Actions | levels_completed | RESET count |
|-----|---------|-----------------|-------------|
| ls20 | 51 | **0** | 1 |
| vc33 | 6 | **0** | 0 |

Score Kaggle v7.0 (L-023) : **RHAE = 0.14** — insuffisant.

---

## 3. Architecture v10.0 — LuCY Noyau Cognitif Natif

### Principe directeur

LuCY v10.0 ne cherche plus à optimiser des statistiques d'actions.
Elle **observe**, **raisonne** et **planifie** directement sur la grille ARC.

### Modules cognitifs natifs

```
┌─────────────────────────────────────────────────────────────────┐
│  LuCY v10.0 — Noyau Cognitif Natif                              │
│                                                                  │
│  ┌──────────────────┐   ┌───────────────────────────────────┐  │
│  │  PERCEPTEUR      │   │  MÉMOIRE ÉPISODIQUE               │  │
│  │  _GridPerceptor  │   │  _EpisodicMemory                  │  │
│  │                  │   │  - patterns vus → actions réussies│  │
│  │  - grille 2D     │   │  - fingerprint → solution         │  │
│  │  - couleurs      │   │  - score_per_action               │  │
│  │  - symétries     │   └───────────────────────────────────┘  │
│  │  - delta spatial │                                           │
│  └────────┬─────────┘   ┌───────────────────────────────────┐  │
│           │              │  MOTEUR D'INFÉRENCE               │  │
│           ▼              │  _CognitiveEngine                 │  │
│  ┌──────────────────┐   │  - score chaque action disponible  │  │
│  │  FEATURES        │   │  - pondère par : perception +      │  │
│  │  - symétrie H/V  │   │    mémoire + diversité + progrès   │  │
│  │  - dominance     │   │  - sélection déterministe          │  │
│  │    couleur       │   └───────────────────────────────────┘  │
│  │  - complexité    │                                           │
│  │  - delta_mass    │                                           │
│  └──────────────────┘                                           │
└─────────────────────────────────────────────────────────────────┘
```

### Décision de sélection d'action v10.0

```
score(action) = w_mem  × memory_score(action)   # actions qui ont déjà marché
              + w_prog × progress_bonus(action)  # actions qui ont changé le frame
              + w_div  × diversity_bonus(action) # actions peu essayées
              + w_pct  × perception_hint(action) # action cohérente avec la grille
```

Pas de LLM. Pas d'appel externe. Calcul entièrement local en Python natif.

---

## 4. Plan d'implémentation v10.0

| Module | Classe | Rôle |
|--------|--------|------|
| Percepteur | `_GridPerceptor` | Extraire features de la grille (symétrie, couleur dominante, complexité, delta spatial) |
| Mémoire épisodique | `_EpisodicMemory` | Stocker fingerprint→actions réussies, score cumulé par action |
| Moteur cognitif | `_CognitiveEngine` | Combiner scores, sélectionner action optimale |
| Agent | `MyAgent` | Implémenter le contrat ARC-AGI-3 (is_done + choose_action) |
| Logger | `_KaggleForensicLogger` | Conservé depuis v9.0 (nanoseconde, stdout) |

---

## 5. Nommage officiel

Suite à la question de l'utilisateur sur "Noyau cognitif" vs "Cognitive Agent" :

**Décision D-LUCY-001 règle ce débat définitivement.**

| Contexte | Terme officiel |
|----------|---------------|
| Classe interne (`src/lucy/kernel/`) | **LuCY Noyau Cognitif** (terme technique précis, français) |
| Docstring agent Kaggle (`agent/my_agent.py`) | **LuCY Cognitive Agent** (D-004 : code en anglais) |
| Communication publique | **LuCY** (sans qualificatif — LuCY est son propre type de modèle) |

Les deux termes peuvent coexister car ils désignent des niveaux différents :
- "Noyau Cognitif" = la couche raisonnement interne
- "Cognitive Agent" = le wrapper d'interface Kaggle

**Il n'y a PAS de dérive — il y a deux niveaux d'abstraction distincts.**

---

## 6. Prochaine étape

Implémentation LuCY v10.0 → rapport L-029.

**CERTIFIED_100=false** | **unique_human_proven=false** | **Mode DEBUG actif**

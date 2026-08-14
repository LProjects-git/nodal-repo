# nodal

Graphe d'appels interactif façon **éditeur de nœuds Blender**, pour du code
**Python** et **C/C++**. Zéro dépendance (stdlib uniquement), sortie HTML autonome.

## Usage

Un fichier **ou un dossier entier** :

```python
import nodal
nodal.render("mon_script.py", "graphe.html")
nodal.render("mon_projet/",   "graphe.html")   # projet complet
nodal.render("moteur.cpp",    "resume.md")     # export texte
```

```bash
python -m nodal mon_projet/ -o graphe.html
python -m nodal mon_projet/ --lang cpp --ignore=tests --max-files 200
python -m nodal moteur.cpp --backend clang --clang-arg=-Iinclude
```

Extensions reconnues : `.py .pyw` — `.cpp .cc .cxx .c++ .hpp .hh .hxx .h .c`

## Projets multi-fichiers

Sur un dossier, nodal analyse chaque fichier puis **recroise les appels non
résolus avec l'index global des définitions** : `main.py` qui appelle
`engine.load()` est relié à `core/engine.py::Engine.load`, même à travers les
imports (`from core.engine import Engine`) ou, en C++, entre un header et son
`.cpp`. Le langage majoritaire du dossier l'emporte, pour ne pas mélanger deux
graphes ; forcer avec `--lang`. Dossiers ignorés par défaut : `.git`,
`__pycache__`, `node_modules`, `venv`, `build`, `dist`, `vendor`…

Un fichier au code invalide n'interrompt pas l'analyse : il est signalé et
sauté (`graph.meta["skipped"]`).

## Fonctions inconnues

Chaque appel non résolu est classé, jamais mélangé :

| nœud | signification |
|---|---|
| 🟠 `json`, `std`, `re` | bibliothèque ou module importé |
| 🟠 `builtins` | fonction native du langage |
| 🔴 `?` | **définition introuvable** — ni dans le projet, ni via un import |

Le nœud rouge `?` liste les symboles appelés dont le code n'existe nulle part
dans ce qui a été analysé : coquille, fonction supprimée, macro, ou dépendance
hors du périmètre. La CLI les résume en fin d'exécution.

Les appels sur des données (`parts.append`, `m.group`) ne sont pas comptés
comme des fonctions : nodal connaît les variables locales, les fermetures et
les globales du module, et les écarte.

## Ce que fait l'analyse

- **Fonctions & méthodes** avec leur code source complet dans chaque nœud
- **Graphe d'appels** : un fil part de la *ligne exacte* de l'appel (prise jaune ◌)
  vers l'en-tête de la fonction appelée
- **Groupes** : cadre en pointillés par `class`, `struct` ou `namespace`, placés
  en couloirs pour ne jamais se chevaucher
- **Appels externes** : nœuds orange (modules, `std::`, builtins, macros)
- **Erreurs gérées** : fichier introuvable, encodage, extension inconnue,
  syntaxe invalide → `AnalysisError` lisible, jamais de trace Python brute

### Python (module `ast`)
`self.m()`, `Classe()` → `__init__`, `obj = Classe(); obj.m()`,
`self.attr = Classe()` puis `self.attr.m()`, **fonctions imbriquées et
fermetures** (une fonction interne appelant sa sœur est bien reliée),
builtins regroupés.

### C/C++ — deux backends
| | scanner (défaut) | libclang |
|---|---|---|
| Dépendance | aucune | `pip install libclang` |
| Définitions hors-ligne `void Foo::bar()` | ✅ | ✅ |
| Surcharges | par nombre d'arguments | exact |
| Héritage `class D : public B` | ✅ | ✅ |
| Templates | types locaux `Box<int> b;` | exact |
| Macros / préprocesseur | neutralisé | développé |
| En-têtes système manquants | insensible | dégradé |

Le scanner est le défaut parce qu'il ne dépend de rien et reste fiable même
sans les `-I` du projet. Passe à `--backend clang` si tu peux fournir les
vraies options de compilation.

## Gros projets

Au-delà de quelques centaines de fonctions, tout afficher n'a plus de sens.
Trois niveaux de réduction, du plus ciblé au plus large :

```bash
# 1. le voisinage d'une fonction — la meilleure option
python -m nodal projet/ --focus Tracking::GrabImage --depth 2 -o g.html

# 2. écarter le bruit
python -m nodal projet/ --no-externals --max-lines 20 -o g.html

# 3. restreindre le périmètre
python -m nodal projet/src --ignore=Thirdparty --ignore=Examples -o g.html
```

`--focus` retient les fonctions dont l'identifiant contient le texte donné,
plus leur voisinage à `--depth` sauts ; `--direction callers` ou `callees`
limite le sens du parcours. La CLI prévient d'elle-même quand un graphe
dépasse 400 nœuds.

Dans l'affichage, **double-cliquer sur un nœud isole son voisinage** et
replace le reste : on explore de proche en proche sans régénérer le fichier,
et « Tout réafficher » revient en arrière. Au-delà de 120 nœuds, le code est
replié au départ et n'est construit qu'au dépliage — le bouton « Replier
tout / Déplier tout » agit sur les nœuds visibles.

### Performances

Mesuré sur un projet synthétique de 750 fonctions et 2250 appels :

| | avant | après |
|---|---|---|
| Construction de la page | 8,8 s | 2,1 s |
| Redessin des fils (par image) | 567 ms | 12 ms |
| Voisinage isolé (32 nœuds) | — | 0,2 ms |

Les fils sont calculés depuis les coordonnées mémorisées plutôt qu'en
interrogeant le navigateur sur la position réelle de chaque élément, ce qui
supprime des milliers de recalculs de mise en page par mouvement de souris ;
le tracé est limité à la zone visible et lissé sur une image.

## Interface

Glisser les nœuds · panoramique sur le fond · zoom molette · recherche et
filtres par type · **filtre par fichier** (projets multi-fichiers) · masquer un
nœud (👁) · replier le code (▾) · sélection → fils animés · « Recentrer ».

Chaque nœud porte un badge indiquant son fichier d'origine, et chaque classe,
`struct` ou `namespace` occupe un couloir horizontal distinct.

## API

```python
from nodal import analyze, AnalysisError

try:
    g = analyze("mon_projet/", ignore={"tests"})
except AnalysisError as e:
    print("échec :", e)
else:
    for e in g.edges:
        print(e.src, "→", e.dst, f"(ligne {e.lineno})")

    # fonctions appelées dont la définition reste introuvable
    for x in g.externals:
        if x.kind == "unknown":
            print("introuvables :", x.members)

    # code mort : jamais appelé
    called = {e.dst for e in g.edges}
    print("jamais appelé :", [f.id for f in g.functions if f.id not in called])
```

`g.functions`, `g.classes`, `g.externals`, `g.edges` sont des dataclasses —
pratique pour détecter le code mort ou brancher tes propres traitements.

## Compatibilité

Windows, macOS et Linux, Python ≥ 3.10, aucune dépendance. Testé sur les
points qui piègent habituellement le portage : BOM UTF-8 en tête de fichier,
fins de ligne CRLF, noms de fichiers accentués, séparateurs `\` (les chemins
sont normalisés en `/` dans les identifiants), et consoles Windows en cp1252
ou cp437 — l'affichage retombe sur de l'ASCII plutôt que de planter.

Le HTML produit est autonome et s'ouvre dans n'importe quel navigateur récent.

## Structure

```
nodal/
├── __init__.py    # API publique : render(), analyze() — dispatch par extension
├── model.py       # dataclasses partagées + placement en couches
├── analyzer.py    # frontend Python (module ast)
├── cpp.py         # frontend C/C++ (scanner sans dépendance + libclang)
├── project.py     # parcours d'un dossier + résolution inter-fichiers
├── renderer.py    # graphe → HTML autonome ou Markdown
└── __main__.py    # CLI
```

Ajouter un langage = écrire un frontend qui produit un `Graph` ; le rendu est
partagé.

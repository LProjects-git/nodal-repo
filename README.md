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

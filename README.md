# nodal

Graphe d'appels interactif façon **éditeur de nœuds Blender**, pour du code
**Python** et **C/C++**. Zéro dépendance (stdlib uniquement), sortie HTML autonome.

## Usage

```python
import nodal
nodal.render("mon_script.py", "graphe.html")
nodal.render("moteur.cpp",    "graphe.html")   # ou "resume.md"
```

```bash
python -m nodal moteur.cpp -o graphe.html
python -m nodal moteur.cpp --backend clang --clang-arg=-Iinclude
```

Extensions reconnues : `.py .pyw` — `.cpp .cc .cxx .c++ .hpp .hh .hxx .h .c`

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
`self.attr = Classe()` puis `self.attr.m()`, builtins regroupés.

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
filtres par type · masquer un nœud (👁) · replier le code (▾) · sélection →
fils animés · « Recentrer » recadre la vue.

## API

```python
from nodal import analyze, AnalysisError

try:
    g = analyze("moteur.cpp", backend="scanner")
except AnalysisError as e:
    print("échec :", e)
else:
    for e in g.edges:
        print(e.src, "→", e.dst, f"(ligne {e.lineno})")
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
├── renderer.py    # graphe → HTML autonome ou Markdown
└── __main__.py    # CLI
```

Ajouter un langage = écrire un frontend qui produit un `Graph` ; le rendu est
partagé.

# nodal

Graphe d'appels interactif façon **éditeur de nœuds Blender** pour un fichier Python.
Zéro dépendance (stdlib uniquement), sortie HTML autonome.

## Usage

```python
import nodal
nodal.render("mon_script.py", "graphe.html")   # ou "graphe.md" pour un résumé texte
```

```bash
python -m nodal mon_script.py -o graphe.html
```

## Ce que fait l'analyse

- **Fonctions & méthodes** extraites via l'AST, code source complet affiché dans chaque nœud
- **Graphe d'appels** : un fil part de la *ligne exacte* de l'appel (prise jaune ◌) vers l'en-tête de la fonction appelée
- **Classes** : cadre en pointillés regroupant les méthodes, avec étiquette `class Nom`
- **Inférence légère** : `self.m()`, `Classe()` → `__init__`, `obj = Classe(); obj.m()`, `self.attr = Classe()` puis `self.attr.m()`
- **Appels externes** : nœuds orange (modules importés, builtins regroupés)
- **Erreurs gérées** : fichier introuvable, encodage, `SyntaxError` avec ligne → `AnalysisError` lisible

## Interface

Glisser les nœuds · panoramique sur le fond · zoom molette · recherche/filtre par
type · masquer un nœud (👁) · replier le code (▾) · sélection → fils animés ·
« Recentrer » recadre la vue.

## Structure

```
nodal/
├── __init__.py    # API publique : render(), analyze()
├── analyzer.py    # AST → graphe (dataclasses) + placement en couches
├── renderer.py    # graphe → HTML autonome (ou Markdown)
└── __main__.py    # CLI
```

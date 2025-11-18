# Scraper BoursoBank

Ce projet a pour objectif de récupérer les données des opérations bancaires depuis le site web de BoursoBank.

Il utilise la librairie [Playwright](https://playwright.dev/python/) pour naviguer sur le site de la banque.

## Format des données

Le scraper récupère les données au format JSON.

Il s'agit du fichier json fourni par l'api de BoursoBank directement.

Les principaux champs incluent :

- **Identifiant unique**
- Date de l’opération
- Date de valeur
- Plusieurs libellés
- Montant
- Montant en devise (si applicable)
- Indication de lieu (souvent incorrect)

## Résultat

Les fichiers sont enregistrés dans un répertoire nommé `data/transactions`.

Ils sont rangés des sous-répertoires `année/mois/jour`.

Les opérations en traitement sont enregistrées dans le répertoire `authorization/new`.

Les anciennes opérations en traitement sont enregistrées dans le répertoire `authorization/old`.

## Installation

### Prérequis

- Python 3.13 ou supérieur

### Installation

`boursobank-scraper` peut être installé via la commande `pip install` comme n'importe quel module python, mais la méthode recommandée est d'utiliser le gestionnaire de paquets [uv](https://docs.astral.sh/uv/) et en particulier la commande `uv tool install`

```bash
uv tool install boursobank-scraper
```

Celle-ci installe la commande `boursobank-scraper` directement accessible depuis le terminal.

Installation du navigateur Chromium pour playwright.


```bash
playwright-bbs install chromium
```

> La commande playwright-bbs est identique à la commande playwright du projet [Playwright](https://playwright.dev/python/). Elle est juste nommée différemment pour ne pas interférer avec une autre version qui serait installée en parallèle.

### Mise à jour

Pour mettre à jour `boursobank-scraper`, exécutez simplement la commande :

```bash
uv tool upgrade boursobank-scraper
```


### Configuration

Le programme a besoin d'un répertoire contenant le fichier de configuration `config.yaml`.

Créez un répertoire `boursobank-data`

```bash
mkdir ~/boursobank-data
cd ~/boursobank-data
```

Ajoutez-y un fichier `config.yaml` avec les informations de connexion à la banque.

```yaml
---
username: 12345678
password: 87654321 # optionnel
password_by_keyring: true # optionnel, ajoute la gestion du keyring
headless: false # optionnel, défaut : False
timeoutMs: 15000 # optionnel, défaut : 30000 millisecondes
saveTrace: true # optionnel, défaut : false

```

> le mot de passe est chiffré si `password_by_keyring: true`.
>
> `password` et `password_by_keyring:` ne sont pas obligatoire. Dans ce cas, il sera demandé à chaque exécution.

Le paramètre `headless` peut prendre la valeur `false`. Dans ce cas, le navigateur sera affiché lors du scrapping. Sinon, le chargement aura lieu en tâche de fond.

Le paramètre `timeoutMs` définit le temps maximum d'attente après chaque chargement de page.

Le paramètre `saveTrace` définit si les traces de l'exécution seront sauvegardées dans un fichier `debug/trace.zip`. Par défaut, la trace n'est pas sauvegardée.

> **Attention : le mot de passe est visible dans la trace.**

## Exécution

Placez vous dans le répertoire boursobank-data et exécutez la commande :

```bash
cd ~/boursobank-data
boursobank-scraper
```

Ou, appelez directement la commande avec le répertoire data en paramètre :

```bash
boursobank-scraper --data-folder ~/boursobank-data
```

Pour ajouter le mot de passe dans le keyring:

```bash
python -m keyring set boursobank <BoursoBank ID>
```

Pour le récupérer:

```bash
python -m keyring get boursobank <BoursoBank ID>
```

Sinon, indiquez le mot de passe si vous ne l'avez pas spécifié dans le fichier `config.yaml`.

Si vous avez spécifié `false` pour `headless`, le navigateur sera affiché lors du scrapping. Sinon, le chargement aura lieu en tâche de fond.

A la première exécution, le script va tenter de télécharger les informations pour toutes les opérations disponibles.

Les fois suivantes, seules les nouvelles opérations seront téléchargées.

Une fois le script exécuté, les fichiers de transactions sont disponibles dans les répertoires `boursobank-scraper/transactions/[année]/[mois]/[jour]`.

> **Attention** : ne supprimez pas les fichiers json dans ces répertoires, sinon le script les retéléchargera la prochaine fois, et le chargement sera bien plus long.
>
> Les anciennes opérations peuvent toutefois être supprimées à condition de garder au moins les 50 dernières sur chaque compte.

#### Synthèse des comptes

Un fichier `accounts.json` est régénéré à chaque exécution. Ilcontient la liste des comptes bancaires. Chaque compte est représenté par un objet JSON avec les informations suivantes :
- `id`: identifiant unique du compte.
- `name`: nom du compte.
- `balance`: solde du compte.
- `link`: lien vers la page du compte.


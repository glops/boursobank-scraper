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

### Installation via uv

```bash
uv tool install boursobank-scraper
```

Installation du navigateur Chromium pour playwright.


```bash
playwright-bbs install chromium
```

> La commande playwright-bbs est identique à la commande playwright du projet [Playwright](https://playwright.dev/python/). Elle est juste nommé différemment pour ne pas interférer avec une autre version qui serait installée en parallèle.


### Configuration

Le programme a besoin d'un répertoire `boursobank-scraper` contenant le fichier de configuration `config.yaml`.

Par défault, ce répertoire est recherché dans l'ordre aux emplacements suivants:
- Dans le répertoire courant : `./boursobank-scraper`
- Dans le répertoire home : `~/boursobank-scraper`
- Dans le répertoire .config : `~/.config/boursobank-scraper`

Ici on prend l'exemple du répertoire home.

Dans votre répertoire home, créez un répertoire `boursobank-scraper`

```bash
mkdir ~/boursobank-scraper
cd ~/boursobank-scraper
```

Ajoutez-y un fichier `config.yaml` avec les informations de connexion à la banque.

```yaml
---
username: 12345678
password: 87654321
headless: false
```

> **Attention : le mot de passe n'est pas crypté !**
>
> Il n'est pas obligatoire. Dans ce cas, il sera demandé à chaque exécution.

Le paramètre `headless` peut prendre la valeur `false`. Dans ce cas, le navigateur sera affiché lors du scrapping. Sinon, le chargement aura lieu en tâche de fond.

### Exécution

Placez vous dans le répertoire parent du répertoire boursobank-scraper et exécutez la commande :

```bash
$ boursobank-scraper
```

Indiquez le mot de passe si demandé.

Une fois le script exécuté, les fichiers de transactions sont disponibles dans les répertoires `boursobank-scraper/transactions/[année]/[mois]/[jour]`.

Le fichier `boursobank-scraper/accounts.json` contient la liste des comptes bancaires. Chaque compte est représenté par un objet JSON avec les informations suivantes :
- `id`: identifiant unique du compte.
- `name`: nom du compte.
- `balance`: solde du compte.
- `link`: lien vers la page du compte.

# Développement


## Création d'un nouvelle version

```bash
uv version --bump major
uv version --bump minor
uv version --bump patch
```
Puis push

## Publication de la version

```bash
git tag -a "v$(uv version --short)" -m "v$(uv version --short)"
git push --tags
```
Le build et la publication du package sur pypi sont ensuite automatique.

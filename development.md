# Développement


## Création d'un nouvelle version

```bash
uv version --bump major
uv version --bump minor
uv version --bump patch
```
Puis commit et push
```bash
git add pyproject.toml uv.lock
git commit -m "bump version"
git push
```

## Publication de la version

```bash
git tag -a "v$(uv version --short)" -m "v$(uv version --short)"
git push --tags
```
Le build et la publication du package sur pypi sont ensuite automatique.

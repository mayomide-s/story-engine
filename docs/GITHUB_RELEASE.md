# GitHub Release Handoff

## Before You Push

- Confirm `git status` is clean
- Confirm `.env` is not tracked
- Confirm `.env.example` contains only placeholder values
- Run:

```bash
pytest -q
npm run build
```

## Add A GitHub Remote

If this repo does not already have a remote, create the GitHub repository first, then add it locally:

```bash
git remote add origin https://github.com/YOUR-ORG/YOUR-REPO.git
```

Verify it:

```bash
git remote -v
```

## Push Commits

Push the current branch:

```bash
git push -u origin HEAD
```

## Push Tags

Push the release tags:

```bash
git push origin v1.0-local-mvp
git push origin v1.0.1-runway-verified
```

Or push all local tags:

```bash
git push --tags
```

## What Not To Commit

- `.env`
- provider API keys
- Cloudflare R2 secrets
- local generated media you do not intend to preserve in git
- Docker temp/debug output

## Clone And Start Later

Clone the repo:

```bash
git clone https://github.com/YOUR-ORG/YOUR-REPO.git
cd YOUR-REPO
```

Restore local env config:

```bash
cp .env.example .env
```

Then edit `.env` with your local values and start the stack:

```bash
docker-compose up --build
```

## Restore `.env` From `.env.example`

If `.env` is missing:

```bash
cp .env.example .env
```

Then fill in only the values needed for the mode you want:

- `mock/local`
- `mock/r2`
- `runway/r2`

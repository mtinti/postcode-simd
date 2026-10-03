#!/usr/bin/env bash
# Update the gh-pages branch, which GitHub Pages serves, then have Pages rebuild it and wait.
#
#   pages_publish.sh publish <branch> <built site dir>   main replaces all but preview/; another
#                                                        branch replaces only its own preview folder
#   pages_publish.sh remove  <branch>                    removes that branch's preview folder
#   pages_publish.sh dest    <branch>                    prints the folder, "" for main
#
# Every attempt starts from the latest gh-pages and applies only this run's change, so two runs
# publishing different branches at once both land: a rejected push is retried from the new state.
# A push made with GITHUB_TOKEN does not itself trigger a Pages build, so one is requested
# explicitly, and the script fails unless that build completes.
set -euo pipefail

dest_for() {
  # A readable name plus a hash of the exact branch name: feature/a and feature-a never collide.
  local branch="$1"
  [ "$branch" = "main" ] && { echo ""; return; }
  local readable hash
  readable=$(printf '%s' "$branch" | tr -c 'A-Za-z0-9._-' '-' | cut -c1-60)
  hash=$(printf '%s' "$branch" | sha256sum | cut -c1-8)
  echo "preview/${readable}-${hash}"
}

mode="$1"; branch="$2"; site="${3:-}"
dest=$(dest_for "$branch")
[ "$mode" = "dest" ] && { echo "$dest"; exit 0; }

remote="https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
git config --global user.name "github-actions[bot]"
git config --global user.email "41898282+github-actions[bot]@users.noreply.github.com"

pushed=""
for attempt in 1 2 3 4 5; do
  work=$(mktemp -d)
  if git ls-remote --exit-code --heads "$remote" gh-pages > /dev/null; then
    git clone --quiet --depth 1 --branch gh-pages "$remote" "$work/pages"
  elif [ "$mode" = "remove" ]; then
    echo "no gh-pages branch: nothing to remove"; exit 0
  else
    git init --quiet "$work/pages" && git -C "$work/pages" checkout --quiet --orphan gh-pages
  fi
  pages="$work/pages"
  case "$mode" in
    publish)
      if [ -z "$dest" ]; then
        find "$pages" -mindepth 1 -maxdepth 1 ! -name .git ! -name preview -exec rm -rf {} +
        cp -R "$site/." "$pages/"
      else
        rm -rf "${pages:?}/$dest"
        mkdir -p "$pages/$dest"
        cp -R "$site/." "$pages/$dest/"
      fi
      touch "$pages/.nojekyll"
      message="Publish ${branch} at ${GITHUB_SHA::7}${dest:+ to $dest}" ;;
    remove)
      [ -n "$dest" ] || { echo "main is never removed"; exit 1; }
      [ -d "$pages/$dest" ] || { echo "no preview for $branch at $dest"; exit 0; }
      git -C "$pages" rm -r --quiet "$dest"
      message="Remove the preview of ${branch} ($dest)" ;;
    *) echo "unknown mode $mode"; exit 2 ;;
  esac
  git -C "$pages" add -A
  if git -C "$pages" diff --cached --quiet; then echo "nothing changed"; exit 0; fi
  git -C "$pages" commit --quiet -m "$message"
  if git -C "$pages" push --quiet "$remote" HEAD:gh-pages; then pushed=yes; break; fi
  echo "push rejected (attempt $attempt): gh-pages moved; retrying from its latest state"
  sleep $(( attempt * 5 + RANDOM % 5 ))
done
[ -n "$pushed" ] || { echo "could not update gh-pages after 5 attempts"; exit 1; }

# Pages rebuilds only when asked: request a build and wait until a completed build contains this
# run's commit (it may be a later one, if another run published meanwhile).
commit=$(git -C "$pages" rev-parse HEAD)
gh api -X POST "repos/${GITHUB_REPOSITORY}/pages/builds" > /dev/null
for i in $(seq 1 60); do
  sleep 10
  read -r status built < <(gh api "repos/${GITHUB_REPOSITORY}/pages/builds/latest" --jq '"\(.status) \(.commit)"')
  contains=$(gh api "repos/${GITHUB_REPOSITORY}/compare/${commit}...${built}" --jq '.status' 2>/dev/null || echo unknown)
  case "$contains" in
    identical|ahead)
      case "$status" in
        built) echo "Pages built ${built::7}, which contains ${commit::7}"; exit 0 ;;
        errored) echo "Pages build of ${built::7} errored"; exit 1 ;;
      esac ;;
  esac
  echo "waiting: latest Pages build ${built::7} is ${status}"
done
echo "Pages did not finish a build containing ${commit::7} in time"; exit 1

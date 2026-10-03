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
# A push made with GITHUB_TOKEN does not itself trigger a Pages build, so the script always ends by
# making sure a completed build contains the current gh-pages, requesting one if not, and fails
# otherwise. It does so even when this run changed nothing: a rerun after a push that landed but
# whose build request failed must deploy, never report success.
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

pushed=""; unchanged=""
for attempt in 1 2 3 4 5; do
  work=$(mktemp -d)
  if git ls-remote --exit-code --heads "$remote" gh-pages > /dev/null; then
    git clone --quiet --depth 1 --branch gh-pages "$remote" "$work/pages"
  elif [ "$mode" = "remove" ]; then
    echo "no gh-pages branch: nothing to remove or deploy"; exit 0
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
      if [ ! -d "$pages/$dest" ]; then echo "no preview for $branch at $dest"; unchanged=yes; break; fi
      git -C "$pages" rm -r --quiet "$dest"
      message="Remove the preview of ${branch} ($dest)" ;;
    *) echo "unknown mode $mode"; exit 2 ;;
  esac
  git -C "$pages" add -A
  if git -C "$pages" diff --cached --quiet; then echo "nothing changed on gh-pages"; unchanged=yes; break; fi
  git -C "$pages" commit --quiet -m "$message"
  if git -C "$pages" push --quiet "$remote" HEAD:gh-pages; then pushed=yes; break; fi
  echo "push rejected (attempt $attempt): gh-pages moved; retrying from its latest state"
  sleep $(( attempt * 5 + RANDOM % 5 ))
done
[ -n "$pushed" ] || [ -n "$unchanged" ] || { echo "could not update gh-pages after 5 attempts"; exit 1; }

# Make sure a completed Pages build contains the current gh-pages, whether or not this run changed
# it: request a build only when none does, then wait. A later build (another run published since)
# that contains it counts.
commit=$(git -C "$pages" rev-parse HEAD)
contains() {   # does build commit $1 contain $commit?
  [ "$1" = "$commit" ] && return 0
  case "$(gh api "repos/${GITHUB_REPOSITORY}/compare/${commit}...$1" --jq '.status' 2>/dev/null || echo unknown)" in
    identical|ahead) return 0 ;; *) return 1 ;;
  esac
}
while read -r status built; do
  if [ "$status" = "built" ] && contains "$built"; then
    echo "Pages already built ${built::7}, which contains ${commit::7}"; exit 0
  fi
done < <(gh api "repos/${GITHUB_REPOSITORY}/pages/builds?per_page=5" --jq '.[] | "\(.status) \(.commit)"' 2>/dev/null || true)
gh api -X POST "repos/${GITHUB_REPOSITORY}/pages/builds" > /dev/null
echo "requested a Pages build for ${commit::7}"
# A request can produce two builds a second apart: the first is cancelled by the second and recorded
# as "errored: Page build failed", while the second builds. So read the recent builds, not only the
# latest: succeed if any build containing the commit is built; fail only when every such build has
# errored and none has been queued or building for three checks in a row.
settled_errors=0
for i in $(seq 1 60); do
  sleep 10
  outcome=""; pending=""
  while read -r status built; do
    contains "$built" || continue
    case "$status" in
      built) outcome=built; break ;;
      errored) [ -n "$outcome" ] || outcome=errored ;;
      *) pending=yes ;;
    esac
  done < <(gh api "repos/${GITHUB_REPOSITORY}/pages/builds?per_page=5" --jq '.[] | "\(.status) \(.commit)"')
  if [ "$outcome" = built ]; then echo "Pages built a commit containing ${commit::7}"; exit 0; fi
  if [ "$outcome" = errored ] && [ -z "$pending" ]; then
    settled_errors=$((settled_errors + 1))
    [ "$settled_errors" -ge 3 ] && { echo "every Pages build containing ${commit::7} errored"; exit 1; }
  else
    settled_errors=0
  fi
  echo "waiting for a Pages build of ${commit::7}"
done
echo "Pages did not finish a build containing ${commit::7} in time"; exit 1

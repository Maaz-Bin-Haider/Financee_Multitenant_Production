#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

readonly APPROVED_REPOSITORY="Maaz-Bin-Haider/financee_pk_backup"
: "${GITHUB_BACKUP_REPOSITORY:?Set GITHUB_BACKUP_REPOSITORY}"
: "${GH_TOKEN:?Set a fine-grained token for the backup repository}"
: "${BACKUP_PASSPHRASE_FILE:?Set BACKUP_PASSPHRASE_FILE}"
: "${BACKUP_FILE:?Set BACKUP_FILE to the encrypted DB backup}"

[[ "$GITHUB_BACKUP_REPOSITORY" == "$APPROVED_REPOSITORY" ]] || {
    echo "Refusing unapproved GitHub repository" >&2
    exit 2
}
[[ -f "$BACKUP_FILE" && "$BACKUP_FILE" = /* ]] || {
    echo "BACKUP_FILE must be an existing absolute path" >&2
    exit 2
}
[[ -f "$BACKUP_FILE.sha256" && -s "$BACKUP_PASSPHRASE_FILE" ]] || {
    echo "Checksum sidecar or backup passphrase is missing" >&2
    exit 2
}

backup_basename=$(basename "$BACKUP_FILE")
checksum_basename=$(basename "$BACKUP_FILE.sha256")
if [[ ! "$backup_basename" =~ ^financee-db-([0-9]{8}T[0-9]{6}Z)\.dump\.tar\.enc$ ]]; then
    echo "Backup filename does not match the managed UTC format" >&2
    exit 2
fi
stamp="${BASH_REMATCH[1]}"
tag="db-backup-$stamp"

max_bytes="${GITHUB_BACKUP_MAX_BYTES:-2040109465}"  # 1.9 GiB
warn_bytes="${GITHUB_BACKUP_WARN_BYTES:-1610612736}" # 1.5 GiB
backup_bytes=$(wc -c <"$BACKUP_FILE" | tr -d ' ')
[[ "$max_bytes" =~ ^[0-9]+$ && "$warn_bytes" =~ ^[0-9]+$ ]] || {
    echo "Backup size thresholds must be integers" >&2
    exit 2
}
(( backup_bytes <= max_bytes )) || {
    echo "Encrypted backup exceeds the configured GitHub safety limit" >&2
    exit 4
}
if (( backup_bytes >= warn_bytes )); then
    echo "WARNING: encrypted backup is approaching the GitHub asset limit" >&2
fi

repo_private=$(gh api "repos/$GITHUB_BACKUP_REPOSITORY" --jq '.private')
[[ "$repo_private" == "true" ]] || {
    echo "Backup repository must be private" >&2
    exit 5
}

work_dir=$(mktemp -d)
created=0
verified=0
cleanup() {
    status=$?
    rm -rf -- "$work_dir"
    if [[ "$created" == "1" && "$verified" != "1" ]]; then
        gh release delete "$tag" --repo "$GITHUB_BACKUP_REPOSITORY" \
            --cleanup-tag --yes >/dev/null 2>&1 || true
    fi
    return "$status"
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM

git_sha=$(git -C .. rev-parse HEAD 2>/dev/null || printf 'unknown')
release_notes="$work_dir/release-notes.txt"
cat >"$release_notes" <<EOF
Financee encrypted PostgreSQL recovery point.

- Created at (UTC): $stamp
- Application Git SHA: $git_sha
- Backup format: financee-db-backup-v1
- Encrypted bytes: $backup_bytes
- Retention class: daily (monthly retention is selected automatically)
EOF

if gh release view "$tag" --repo "$GITHUB_BACKUP_REPOSITORY" >/dev/null 2>&1; then
    echo "Refusing to overwrite existing recovery point $tag" >&2
    exit 6
fi

echo "==> Creating private GitHub release $tag"
gh release create "$tag" "$BACKUP_FILE" "$BACKUP_FILE.sha256" \
    --repo "$GITHUB_BACKUP_REPOSITORY" \
    --title "Financee DB backup $stamp" \
    --notes-file "$release_notes"
created=1

echo "==> Downloading release assets for independent remote verification"
download_dir="$work_dir/download"
mkdir -m 700 "$download_dir"
gh release download "$tag" --repo "$GITHUB_BACKUP_REPOSITORY" \
    --dir "$download_dir" \
    --pattern "$backup_basename" \
    --pattern "$checksum_basename"
[[ -s "$download_dir/$backup_basename" &&
   -s "$download_dir/$checksum_basename" ]]
(
    cd "$download_dir"
    sha256sum -c "$checksum_basename"
)

verify_dir="$work_dir/verify"
mkdir -m 700 "$verify_dir"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
    -pass "file:$BACKUP_PASSPHRASE_FILE" \
    -in "$download_dir/$backup_basename" |
    tar -xf - -C "$verify_dir"
(
    cd "$verify_dir"
    sha256sum -c SHA256SUMS
)
grep -qx "format=financee-db-backup-v1" "$verify_dir/manifest.txt"
docker compose -f docker-compose.yml exec -T db \
    pg_restore --list <"$verify_dir/database.dump" >/dev/null
verified=1

echo "==> Applying pattern-safe retention after successful verification"
releases_json="$work_dir/releases.json"
gh api --paginate "repos/$GITHUB_BACKUP_REPOSITORY/releases?per_page=100" \
    --slurp >"$work_dir/release-pages.json"
jq 'add' "$work_dir/release-pages.json" >"$releases_json"
while IFS= read -r expired_tag; do
    [[ -n "$expired_tag" ]] || continue
    gh release delete "$expired_tag" --repo "$GITHUB_BACKUP_REPOSITORY" \
        --cleanup-tag --yes
done < <(
    python3 database_backup_retention.py \
        --keep-daily "${GITHUB_BACKUP_KEEP_DAILY:-30}" \
        --keep-monthly "${GITHUB_BACKUP_KEEP_MONTHLY:-12}" \
        --protect "$tag" <"$releases_json"
)

trap - EXIT HUP INT TERM
rm -rf -- "$work_dir"
echo "GITHUB_BACKUP_REPOSITORY=$GITHUB_BACKUP_REPOSITORY"
echo "GITHUB_BACKUP_RELEASE=$tag"
echo "GITHUB_BACKUP_BYTES=$backup_bytes"
echo "GITHUB_BACKUP_REMOTE_VERIFIED=true"
echo "GITHUB_BACKUP_RESULT=PASS"

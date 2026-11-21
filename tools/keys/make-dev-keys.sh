#!/usr/bin/env bash
# Ensure that KEYDIR/rauc contains a persistent development CA and signer.
# Usage: tools/keys/make-dev-keys.sh [KEYDIR]  (default: local/keys)
# Only ca.cert.pem is copied into the device image. Keep the private keys
# local and retain the CA for as long as any development board trusts it.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
keydir=${1:-$ROOT/local/keys}
rauc_dir=$keydir/rauc

umask 077
mkdir -p -- "$keydir"
# Serialize first use without leaving a lock file in the key directory.
exec {lock_fd}<"$keydir"
flock -x "$lock_fd"
if [ -e "$rauc_dir" ] || [ -L "$rauc_dir" ]; then
	for name in ca.key.pem ca.cert.pem signer.key.pem signer.cert.pem; do
		[ -s "$rauc_dir/$name" ] || {
			echo "Incomplete development keys: missing $rauc_dir/$name. Restore the keys or choose a new key directory." >&2
			exit 1
		}
	done
	exit 0
fi

command -v openssl >/dev/null || { echo "openssl not installed" >&2; exit 1; }
tmp=$(mktemp -d "$keydir/.rauc-keys.XXXXXX")
trap 'rm -rf -- "$tmp"' EXIT
mkdir "$tmp/rauc"

cat > "$tmp/ext.cnf" <<'CONFIG'
[req]
distinguished_name = dn
prompt = no
[dn]
[h713_ca]
basicConstraints = critical, CA:TRUE
keyUsage = critical, keyCertSign, cRLSign
subjectKeyIdentifier = hash
[h713_signer]
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature
extendedKeyUsage = codeSigning
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid
CONFIG
openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$tmp/rauc/ca.key.pem"
openssl req -batch -new -x509 -days 36500 -key "$tmp/rauc/ca.key.pem" -config "$tmp/ext.cnf" \
	-subj "/CN=h713 RAUC CA (development)" -extensions h713_ca -out "$tmp/rauc/ca.cert.pem"
openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$tmp/rauc/signer.key.pem"
openssl req -batch -new -key "$tmp/rauc/signer.key.pem" -config "$tmp/ext.cnf" \
	-subj "/CN=h713 RAUC bundle signer (development)" -out "$tmp/signer.csr"
openssl x509 -req -days 36500 -in "$tmp/signer.csr" -CA "$tmp/rauc/ca.cert.pem" \
	-CAkey "$tmp/rauc/ca.key.pem" -CAserial "$tmp/serial" -CAcreateserial \
	-extfile "$tmp/ext.cnf" -extensions h713_signer -out "$tmp/rauc/signer.cert.pem"
openssl verify -CAfile "$tmp/rauc/ca.cert.pem" "$tmp/rauc/signer.cert.pem" >/dev/null
chmod 0644 "$tmp/rauc/ca.cert.pem" "$tmp/rauc/signer.cert.pem"
mv -T -- "$tmp/rauc" "$rauc_dir"
echo "Generated RAUC development keys in $rauc_dir"

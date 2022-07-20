set -eux
charms="$(find ./federation-gateway-bundle/ -name tox.ini)"
for charm in ${charms}; do
  tox -c "${charm}"
done
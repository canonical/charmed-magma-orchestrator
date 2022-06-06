set -eux

	charms="$(find ./orchestrator-bundle/ -name tox.ini | grep operator)"
		for charm in ${charms}; do
			tox -c "${charm}"
          	done

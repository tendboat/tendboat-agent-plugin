.PHONY: check package clean

TENDBOAT_BINARY ?=
VERSION := $(shell python3 -c 'import json; print(json.load(open("tendboat.lock.json"))["plugin_version"])')

check:
	python3 packaging/verify.py
	python3 -m unittest discover -s tests -p 'test_*.py' -v

package: check
	test -n "$(TENDBOAT_BINARY)" || { echo "set TENDBOAT_BINARY to the executable path"; exit 2; }
	python3 packaging/assemble.py --tendboat-binary $(TENDBOAT_BINARY) --output dist/tendboat-agent-plugin-$(VERSION).tar.gz

clean:
	rm -rf dist/ __pycache__/ packaging/__pycache__/ tests/__pycache__/

spec ?= ../pycharm-community.spec
version := 2026.3.0.1
release_url := https://github.com/JetBrains/intellij-community/releases/download/pycharm%2F$(version)
sources := pycharm-$(version).tar.gz pycharm-$(version)-aarch64.tar.gz

.PHONY: srpm
srpm:
	set -e; for source in $(sources); do curl --fail --location --retry 2 --output $$source $(release_url)/$$source; done
	cp ../pycharm-community.xml ../pycharm-community.desktop ../pycharm-community.metainfo.xml .
	rpmbuild -bs --define "_sourcedir $(CURDIR)" --define "_srcrpmdir $(outdir)" $(spec)

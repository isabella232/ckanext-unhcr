.PHONY: assets docker e2e i18n readme start shell test


list:
	@grep '^\.PHONY' Makefile | cut -d' ' -f2- | tr ' ' '\n'

assets:
	npx grunt concat
	npx grunt postcss

docker:
	docker pull openknowledge/ckan-base:2.8 && \
	docker pull openknowledge/ckan-dev:2.8 && \
	docker-compose -f ../../docker-compose.yml build

e2e:
	npx nightwatch

i18n:
	# docker-compose -f ../../docker-compose.yml exec ckan-dev 'cd /srv/app/src_extensions/ckanext-unhcr && python setup.py extract_messages'
	docker-compose -f ../../docker-compose.yml exec ckan-dev 'cd /srv/app/src_extensions/ckanext-unhcr && python setup.py compile_catalog -l en -f'

readme:
	npx doctoc README.md

start:
	docker-compose -f ../../docker-compose.yml up

shell:
	docker-compose -f ../../docker-compose.yml exec ckan-dev sh

test:
	docker-compose -f ../../docker-compose.yml exec ckan-dev \
	cd /srv/app/src_extensions/ckanext-unhcr && \
	pytest \
		--ckan-ini=test.ini \
		--cov=ckanext.unhcr \
		--cov-report=xml \
		--cov-append \
		--disable-warnings \
		ckanext/unhcr/tests/pt ${ARGS}

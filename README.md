# ckanext-unhcr

![Run tests](https://github.com/okfn/ckanext-unhcr/workflows/Run%20tests/badge.svg?branch=master)
[![codecov](https://codecov.io/gh/okfn/ckanext-unhcr/branch/master/graph/badge.svg?token=WfcRlsn6sE)](https://codecov.io/gh/okfn/ckanext-unhcr)


CKAN extension for the UNHCR RIDL project

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->


- [ckanext-unhcr](#ckanext-unhcr)
  - [Requirements](#requirements)
  - [Setting up environment](#setting-up-environment)
    - [Extension Settings](#extension-settings)
  - [Working with docker](#working-with-docker)
  - [Starting development server](#starting-development-server)
  - [Running unit tests](#running-unit-tests)
    - [Troubleshooting](#troubleshooting)
  - [Running E2E tests](#running-e2e-tests)
  - [Building static assets](#building-static-assets)
  - [Working with i18n](#working-with-i18n)
  - [Logging into container](#logging-into-container)
  - [Updating readme](#updating-readme)
  - [Managing docker](#managing-docker)
  - [Prepare a local environment for running scripts](#prepare-a-local-environment-for-running-scripts)
  - [Generate deposited-dataset schema](#generate-deposited-dataset-schema)
  - [Create data containers and data deposit](#create-data-containers-and-data-deposit)
  - [Create development users](#create-development-users)
  - [Testing email notifications](#testing-email-notifications)
  - [KoBo integration](#kobo-integration)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

## Requirements

This extension is being developed against CKAN 2.9.x

Please follow installation instructions of the software below if needed. Also, take a look inside the `Makefile` to understand what's going on under the hood:
- `docker`
- `docker-compose` (`>= 1.26`)
- `/etc/hosts` contains the `127.0.0.1 ckan-dev` line

For building static assets and running end-to-end tests Node.js is required and can be installed with these commands:

```bash
$ nvm install 10
$ nvm use 10
$ npm install
```

## Setting up environment

Clone the `ckanext-unhcr` repository (assuming that we're inside the `docker-ckan-unhcr-aws/src` directory):

```bash
$ git clone git@github.com:okfn/ckanext-unhcr.git
$ cd ckanext-unhcr
```

It's designed to support live development of extensions. The only one requirement is that the folder with the project should be inside `docker-ckan-unhcr-aws/src`. See `docker-ckan-unhcr-aws` for more information.


### Extension Settings

About external users
```
# days before external user account expires
ckanext.unhcr.external_accounts_expiry_delta=180

# days before notifying about the expiration of the users account
ckanext.unhcr.external_accounts_notify_delta=30

# Max size (MB) for a file to be analyzed with ClamAV
ckan.clamav_max_resource_size=10

# Redis cache in seconds for KoBo get requests. Use 0 to disable cache
ckanext.unhcr.kobo_cache_seconds=600
```


## Working with docker

The whole docker setup is inside the `docker-ckan-unhcr-aws` directory. You can tweak any CKAN instance's aspects there (e.g. patches/cron/etc). To add other CKAN extensions to the work - add its folders to `docker-compose.yml` (see `ckan-dev` volumes).

Pull the latest `ckan-base/dev` images and build the project's images:

```
$ make docker
```

## Starting development server

Let's start the development server. It's recommended to run this command in an additional terminal window because you need it running during the work. All changes to connected extensions will trigger live-reloading of the server:

```bash
$ make start
# see CKAN logs here
```

Now we can visit our local ckan instance at (you can login using `ckan_admin@test1234`):

```
http://ckan-dev:5000/
```

## Running unit tests

We write and store unit tests inside the `ckanext/unhcr/tests`. Prefer to name test files after feature/bug names. To run the tests you should have the development server up and running:

```bash
$ make test
```

To run only selected tests:
- run `$ make test ARGS='-k <pattern>'`

### Troubleshooting

If `ProgrammingError: (psycopg2.errors.UndefinedFunction) function populate_full_text_trigger() does not exist` is thrown running the tests:

* Run `ckan -c /srv/app/ckan.ini datastore set-permissions`
* Grab the generate SQL script and remove the line `\connect "datastore"`
* Connect to the `datastore_test` DB and run the SQL

## Running E2E tests

We write and store E2E tests inside the `tests` directory. Prefer to name test files after feature/bug names. To run the tests you should have the development server up and running:

```bash
$ make e2e
$ npx nightwatch tests/<testname>.js # for a single E2E test
```

See the `how to write E2E tests` guide:
- http://nightwatchjs.org/guide

## Building static assets

We use JS and SCSS preprocessors to compile static assets. Put your scripts/styles inside the `ckanext/unhcr/src` and build it:

```bash
$ make assets
```

Processed styles will be written to the `ckanext/unhcr/fanstatic` folder. The compiled assets should be committed. Any custom images/fonts/etc can be stored directly in `ckanext/unhcr/fanstatic` folder and added to `webassets.yml`.

## Working with i18n

We have (ab)used i18n to make an English-to-English translation which changes the terminology used in CKAN. Occasionally this will need maintenance as the upstream text changes. Example PR: example PR: https://github.com/okfn/ckanext-unhcr/pull/575

See CKAN documentation for more on i18n management.

## Logging into container

To issue commands inside a running container:

```
$ make shell
```

Now you can tweak the running `ckan-dev` docker container from inside. Please take into account that all changes will be lost after the next container restart.

## Updating readme

To update this readme's table of contents run:

```bash
$ make readme
```

## Managing docker

There are a few useful docker commands:

```bash
$ docker ps -aq # list all containers
$ docker stop $(docker ps -aq) # stop all containers
$ docker rm $(docker ps -aq) # remove all containers
$ docker rmi $(docker images -q) # remove all images
$ docker system prune -a --volumes # CAUTION: it will purge all docker projects
$ docker volume rm dockerckan<project>_ckan_storage dockerckan<project>_pg_data # remove project volumes
```

## Prepare a local environment for running scripts

Create a local Python 3 environment, activate it and install requirements.  

```
python3 -m venv /path/to/your/new/env
source /path/to/your/new/env/bin/activate
pip install -r scripts/requirements.txt
```

## Generate deposited-dataset schema

We maintain the `dataset` [schema](/ckanext/unhcr/schemas/dataset.json) manually.  
The `deposited_dataset` [schema](/ckanext/unhcr/schemas/deposited_dataset.json) 
should not be edited by hand. It is the output of running.

```
$ python scripts/generate_deposited_dataset_schema.py
```

The compiled schema should be committed.

## Create data containers and data deposit

It will create all initial data containers and data deposit. For local development `url` should be `https://ckan-dev:5000` and `api_key` from your user profile.

```
$ python scripts/initial_data_containers.py url api_key
$ python scripts/create_data_deposit.py url api_key
$ python scripts/update_container_visibility.py url api_key
```

## Create development users

Create users using command line interface:

```
# Sysadmin
docker-compose -f ../../docker-compose.yml exec ckan-dev ckan -c /srv/app/ckan.ini sysadmin add ckan_sysadmin email=sysadmin@example.com password=testpass
# Depadmin
docker-compose -f ../../docker-compose.yml exec ckan-dev ckan -c /srv/app/ckan.ini user add ckan_depadmin email=depadmin@example.com password=testpass
# Curators
docker-compose -f ../../docker-compose.yml exec ckan-dev ckan -c /srv/app/ckan.ini user add ckan_curator1 email=curator1@example.com password=testpass
docker-compose -f ../../docker-compose.yml exec ckan-dev ckan -c /srv/app/ckan.ini user add ckan_curator2 email=curator2@example.com password=testpass
# Depositors
docker-compose -f ../../docker-compose.yml exec ckan-dev ckan -c /srv/app/ckan.ini user add ckan_user1 email=user1@example.com password=testpass
docker-compose -f ../../docker-compose.yml exec ckan-dev ckan -c /srv/app/ckan.ini user add ckan_user2 email=user2@example.com password=testpass
```

Add admins and and editors to data deposit using web interface:

- make `ckan_depadmin` admin of `data-deposit`
- make `ckan_curator1` and `ckan_curator2` editors of `data-deposit`

## Testing email notifications

We use a fake SMTP server to test email notifications:

- log into https://mailtrap.io/inboxes
- select `Demo Inbox`
- copy SMTP credentials
- past to `docker-ckan-ed:.env` (mail service connection section)
- restart the development server

Now all email sent by `from ckan.lib.mailer import mail_user` should be sent to the `Demo Inbox` at Mailtrap.

## KoBo integration

Internal users are allowed to import data from [KoBoToolbox](https://www.kobotoolbox.org/#home).  
To define where the KoBo instance lives you can configure the `ckanext.unhcr.kobo_url` setting 
(default is `https://kobo.unhcr.org`).

You can read a RIDL integration with KoBo tutorial [here](docs/kobo.md).  
Technical details about the KoBo integration are available [here](docs/kobo-technical.md).  

## Microdata library

Datasets could be published to the [UNHCR Microdata Library](https://microdata.unhcr.org/index.php/home) which uses the [NADA](http://www.ihsn.org/nada) software.  
This is a manual task and is only allowed for Sysdadmins.  

Get collections: `https://microdata.unhcr.org/index.php/api/collections [GET]`.  
Publish dataset `https://microdata.unhcr.org/index.php/api/datasets/create/survey/<IDNO> [POST]`.  
Publish resource `https://microdata.unhcr.org/index.php/api/datasets/<IDNO>/resources [POST]`.  
See published dataset: `https://microdata.unhcr.org/index.php/catalog/<DATASET_ID> [GET]`.  

All calls must include the `X-Api-Key` header.  
To interact via the API we need an API key. To get one we need an admin account in the site. You then use [this endpoint](https://microdata.unhcr.org/api-documentation/catalog-admin/index.html#operation/createApiKey) to get the key.  
Documentation on this API: https://microdata.unhcr.org/api-documentation/catalog-admin/index.html#tag/API-keys
The API KEY **must be** from an administrator user. If not, you'll get the response: `{"status":"ACCESS-DENIED","message":"Access denied"}`.  

The corresponding entity for RIDL datasets in MDL is the [Survey](https://microdata.unhcr.org/api-documentation/catalog-admin/index.html#tag/Survey).

There are two ways of creating a Survey:
* Importing a [DDI](https://microdata.unhcr.org/api-documentation/catalog-admin/index.html#operation/importDDI) (+ RDF) file
* Creating it [directly](https://microdata.unhcr.org/api-documentation/catalog-admin/index.html#operation/createSurvey)

Surveys can be [updated](https://microdata.unhcr.org/api-documentation/catalog-admin/index.html#operation/updateSurvey) as well.

Surveys can be aggregated in collections (via `repositoryid`). We might want to use that to create a generic "Imported from RIDL" one or to match Data Containers on our side.
